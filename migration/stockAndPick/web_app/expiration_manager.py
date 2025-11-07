#!/usr/bin/env python3
"""
Expiration Manager for PCB Inventory System
Handles Date Code (DC) parsing and expiration calculation
"""

import re
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple
from enum import Enum

class ExpirationStatus(Enum):
    """Expiration status levels"""
    FRESH = "fresh"          # Not expired, > 6 months remaining
    WARNING = "warning"      # 1-6 months until expiration
    CRITICAL = "critical"    # < 1 month until expiration
    EXPIRED = "expired"      # Past expiration date
    UNKNOWN = "unknown"      # Cannot determine expiration

class DateCodeParser:
    """Parse various date code formats commonly used in electronics manufacturing"""

    @staticmethod
    def parse_date_code(dc: str) -> Optional[datetime]:
        """
        Parse date code string into datetime object.
        Supports common formats:
        - YYWW (Year Week): 2401 = 2024 Week 1
        - YYYYWW: 202401 = 2024 Week 1
        - YYWK## (with WK): 24WK01 = 2024 Week 1
        - YYYYWK##: 2024WK01 = 2024 Week 1
        - YYMMDD: 240115 = Jan 15, 2024
        - YYYYMMDD: 20240115 = Jan 15, 2024
        - YYDDD (Julian): 24015 = 15th day of 2024
        - YYYYDDD: 2024015 = 15th day of 2024
        """
        if not dc or not dc.strip():
            return None

        dc = dc.strip().upper()

        try:
            # Format: YYWW or YYYYWW (Year Week)
            if re.match(r'^\d{4}$', dc):  # YYWW
                year = int(dc[:2])
                week = int(dc[2:])
                # Assume 20xx for years 00-50, 19xx for 51-99
                year = 2000 + year if year <= 50 else 1900 + year
                return DateCodeParser._week_to_date(year, week)

            elif re.match(r'^\d{6}$', dc):  # Could be YYYYWW or YYMMDD
                # Try as YYYYWW first
                if dc.startswith('20') or dc.startswith('19'):
                    year = int(dc[:4])
                    week = int(dc[4:])
                    if 1 <= week <= 53:
                        return DateCodeParser._week_to_date(year, week)

                # Try as YYMMDD
                year = int(dc[:2])
                month = int(dc[2:4])
                day = int(dc[4:])
                year = 2000 + year if year <= 50 else 1900 + year
                if 1 <= month <= 12 and 1 <= day <= 31:
                    return datetime(year, month, day)

            # Format: YYWK## or YYYYWK##
            elif 'WK' in dc:
                match = re.match(r'^(\d{2,4})WK(\d{1,2})$', dc)
                if match:
                    year = int(match.group(1))
                    week = int(match.group(2))
                    if len(match.group(1)) == 2:
                        year = 2000 + year if year <= 50 else 1900 + year
                    return DateCodeParser._week_to_date(year, week)

            # Format: YYYYMMDD
            elif re.match(r'^\d{8}$', dc):
                year = int(dc[:4])
                month = int(dc[4:6])
                day = int(dc[6:])
                if 1 <= month <= 12 and 1 <= day <= 31:
                    return datetime(year, month, day)

            # Format: YYDDD or YYYYDDD (Julian date)
            elif re.match(r'^\d{5}$', dc):  # YYDDD
                year = int(dc[:2])
                day_of_year = int(dc[2:])
                year = 2000 + year if year <= 50 else 1900 + year
                return DateCodeParser._julian_to_date(year, day_of_year)

            elif re.match(r'^\d{7}$', dc):  # YYYYDDD
                year = int(dc[:4])
                day_of_year = int(dc[4:])
                return DateCodeParser._julian_to_date(year, day_of_year)

        except (ValueError, TypeError):
            pass

        return None

    @staticmethod
    def _week_to_date(year: int, week: int) -> datetime:
        """Convert year and week to datetime (Monday of that week)"""
        if not (1 <= week <= 53):
            raise ValueError(f"Invalid week: {week}")

        # January 4th is always in week 1
        jan4 = datetime(year, 1, 4)
        # Find Monday of week 1
        monday_week1 = jan4 - timedelta(days=jan4.weekday())
        # Add weeks
        return monday_week1 + timedelta(weeks=week - 1)

    @staticmethod
    def _julian_to_date(year: int, day_of_year: int) -> datetime:
        """Convert year and day of year to datetime"""
        if not (1 <= day_of_year <= 366):
            raise ValueError(f"Invalid day of year: {day_of_year}")

        return datetime(year, 1, 1) + timedelta(days=day_of_year - 1)

class ExpirationManager:
    """Manage PCB expiration calculations and status"""

    # Default shelf life in months for different PCB types
    DEFAULT_SHELF_LIFE = {
        'Bare': 36,         # 3 years for bare PCBs
        'Partial': 24,      # 2 years for partial assemblies
        'Completed': 12,    # 1 year for completed assemblies
        'Ready to Ship': 6  # 6 months for ready to ship
    }

    # MSD (Moisture Sensitive Device) shelf life overrides
    MSD_SHELF_LIFE = {
        'Level 1': 96,      # 8 years - not moisture sensitive
        'Level 2': 12,      # 1 year at <30°C/60% RH
        'Level 2a': 4,      # 4 weeks at <30°C/60% RH
        'Level 3': 24,      # 168 hours (1 week) exposure, 1 year floor life
        'Level 4': 12,      # 72 hours exposure, 1 year floor life
        'Level 5': 6,       # 48 hours exposure, 6 months floor life
        'Level 5a': 3,      # 24 hours exposure, 3 months floor life
        'Level 6': 1        # Time on label, 1 month max
    }

    def calculate_expiration_status(self, dc: Optional[str], pcb_type: str,
                                  msd: Optional[str] = None) -> Dict[str, Any]:
        """
        Calculate expiration status based on date code, PCB type, and MSD level.

        Returns:
            Dictionary with expiration information including:
            - status: ExpirationStatus enum
            - manufacture_date: datetime or None
            - expiration_date: datetime or None
            - days_remaining: int (negative if expired)
            - shelf_life_months: int
            - warnings: list of warning messages
        """
        warnings = []
        manufacture_date = None
        expiration_date = None
        days_remaining = 0

        # Parse date code
        if dc:
            manufacture_date = DateCodeParser.parse_date_code(dc)
            if manufacture_date is None:
                warnings.append(f"Could not parse date code: {dc}")

        # Determine shelf life
        shelf_life_months = self.DEFAULT_SHELF_LIFE.get(pcb_type, 12)

        # Check MSD override
        if msd:
            msd_months = self._parse_msd_shelf_life(msd)
            if msd_months is not None:
                shelf_life_months = min(shelf_life_months, msd_months)
                warnings.append(f"MSD level {msd} reduces shelf life")

        # Calculate expiration
        if manufacture_date:
            expiration_date = manufacture_date + timedelta(days=shelf_life_months * 30.44)  # Average month length
            days_remaining = (expiration_date - datetime.now()).days

            # Determine status
            if days_remaining < 0:
                status = ExpirationStatus.EXPIRED
            elif days_remaining < 30:  # Less than 1 month
                status = ExpirationStatus.CRITICAL
            elif days_remaining < 180:  # Less than 6 months
                status = ExpirationStatus.WARNING
            else:
                status = ExpirationStatus.FRESH
        else:
            status = ExpirationStatus.UNKNOWN
            if not dc:
                warnings.append("No date code provided")

        return {
            'status': status,
            'status_text': status.value,
            'manufacture_date': manufacture_date,
            'expiration_date': expiration_date,
            'days_remaining': days_remaining,
            'shelf_life_months': shelf_life_months,
            'warnings': warnings,
            'dc': dc,
            'msd': msd
        }

    def _parse_msd_shelf_life(self, msd: str) -> Optional[int]:
        """Parse MSD string to determine shelf life in months"""
        if not msd:
            return None

        msd_upper = msd.upper().strip()

        # Direct level matches
        for level, months in self.MSD_SHELF_LIFE.items():
            if level.upper() in msd_upper:
                return months

        # Pattern matches
        if re.search(r'LEVEL\s*[1-6]A?', msd_upper):
            match = re.search(r'LEVEL\s*([1-6]A?)', msd_upper)
            if match:
                level_str = f"Level {match.group(1)}"
                return self.MSD_SHELF_LIFE.get(level_str)

        # Look for just the level number
        match = re.search(r'\b([1-6]A?)\b', msd_upper)
        if match:
            level_str = f"Level {match.group(1)}"
            return self.MSD_SHELF_LIFE.get(level_str)

        return None

    def get_expiration_badge_class(self, status: ExpirationStatus) -> str:
        """Get Bootstrap badge class for expiration status"""
        badge_classes = {
            ExpirationStatus.FRESH: 'bg-success',
            ExpirationStatus.WARNING: 'bg-warning text-dark',
            ExpirationStatus.CRITICAL: 'bg-danger',
            ExpirationStatus.EXPIRED: 'bg-dark',
            ExpirationStatus.UNKNOWN: 'bg-secondary'
        }
        return badge_classes.get(status, 'bg-secondary')

    def get_expiration_icon(self, status: ExpirationStatus) -> str:
        """Get Bootstrap icon for expiration status"""
        icons = {
            ExpirationStatus.FRESH: 'bi-check-circle',
            ExpirationStatus.WARNING: 'bi-exclamation-triangle',
            ExpirationStatus.CRITICAL: 'bi-exclamation-circle',
            ExpirationStatus.EXPIRED: 'bi-x-circle',
            ExpirationStatus.UNKNOWN: 'bi-question-circle'
        }
        return icons.get(status, 'bi-question-circle')

    def format_expiration_display(self, expiration_info: Dict[str, Any]) -> str:
        """Format expiration information for display"""
        status = expiration_info['status']
        days_remaining = expiration_info['days_remaining']

        if status == ExpirationStatus.EXPIRED:
            return f"Expired {abs(days_remaining)} days ago"
        elif status == ExpirationStatus.CRITICAL:
            return f"Expires in {days_remaining} days"
        elif status == ExpirationStatus.WARNING:
            months_remaining = days_remaining // 30
            return f"Expires in ~{months_remaining} months"
        elif status == ExpirationStatus.FRESH:
            months_remaining = days_remaining // 30
            return f"Good for ~{months_remaining} months"
        else:
            return "Unknown expiration"

# Example usage and testing
if __name__ == "__main__":
    expiration_manager = ExpirationManager()

    # Test date code parsing
    test_cases = [
        ("2401", "Bare", None),      # 2024 Week 1
        ("24WK01", "Partial", "Level 3"),  # 2024 Week 1 with MSD
        ("240115", "Completed", None),     # Jan 15, 2024
        ("2024015", "Ready to Ship", None), # 15th day of 2024
        ("", "Bare", None),          # No date code
        ("invalid", "Bare", None),   # Invalid date code
    ]

    for dc, pcb_type, msd in test_cases:
        result = expiration_manager.calculate_expiration_status(dc, pcb_type, msd)
        print(f"DC: {dc or 'None'}, Type: {pcb_type}, MSD: {msd or 'None'}")
        print(f"  Status: {result['status_text']}")
        print(f"  Manufacture: {result['manufacture_date']}")
        print(f"  Expiration: {result['expiration_date']}")
        print(f"  Days remaining: {result['days_remaining']}")
        print(f"  Display: {expiration_manager.format_expiration_display(result)}")
        print(f"  Warnings: {result['warnings']}")
        print()