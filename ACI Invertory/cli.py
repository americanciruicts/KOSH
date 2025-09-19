#!/usr/bin/env python3
"""
Document Intelligence CLI Tool

A command-line interface for processing documents with AI analysis.
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.json import JSON
from rich.panel import Panel

from src.config import settings
from src.doc_parser import DocumentParser
from src.ai_pipeline import AIProcessor

console = Console()

@click.group()
@click.version_option(version="1.0.0")
def cli():
    """Document Intelligence CLI - Process any document with AI analysis."""
    pass

@cli.command()
@click.argument('file_path', type=click.Path(exists=True))
@click.option('--model', default='gpt-4o', help='AI model to use (gpt-4o, claude-3-sonnet)')
@click.option('--output-dir', default='outputs', help='Output directory for results')
@click.option('--format', 'output_format', default='json', help='Output format (json, csv)')
@click.option('--extract-pii', is_flag=True, default=True, help='Extract PII information')
@click.option('--verbose', '-v', is_flag=True, help='Verbose output')
def process(file_path: str, model: str, output_dir: str, output_format: str, extract_pii: bool, verbose: bool):
    """Process a single document and extract structured data."""
    
    if verbose:
        console.print(f"[bold blue]Processing:[/bold blue] {file_path}")
        console.print(f"[bold blue]Model:[/bold blue] {model}")
        console.print(f"[bold blue]Output:[/bold blue] {output_dir}")
    
    # Validate inputs
    if not os.path.exists(file_path):
        console.print(f"[red]Error:[/red] File not found: {file_path}")
        sys.exit(1)
    
    # Check API keys
    if model.startswith('gpt') and not settings.openai_api_key:
        console.print("[red]Error:[/red] OpenAI API key not configured")
        sys.exit(1)
    elif model.startswith('claude') and not settings.anthropic_api_key:
        console.print("[red]Error:[/red] Anthropic API key not configured")
        sys.exit(1)
    
    asyncio.run(_process_document(file_path, model, output_dir, output_format, extract_pii, verbose))

async def _process_document(file_path: str, model: str, output_dir: str, output_format: str, extract_pii: bool, verbose: bool):
    """Internal async function to process document."""
    
    parser = DocumentParser()
    ai_processor = AIProcessor()
    
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            
            # Step 1: Parse document
            task1 = progress.add_task("Parsing document...", total=None)
            text, metadata = parser.parse_file(file_path)
            progress.update(task1, description="✅ Document parsed")
            
            if verbose:
                console.print(f"[dim]Extracted {len(text)} characters[/dim]")
                console.print(f"[dim]File type: {metadata.mime_type}[/dim]")
            
            # Step 2: AI Analysis
            task2 = progress.add_task("Analyzing with AI...", total=None)
            analysis = await ai_processor.analyze_document(text, metadata, model)
            progress.update(task2, description="✅ AI analysis complete")
            
            # Step 3: PII Detection
            if extract_pii:
                task3 = progress.add_task("Detecting PII...", total=None)
                pii_data = ai_processor.detect_pii(text)
                analysis.extracted_fields["detected_pii"] = pii_data
                progress.update(task3, description="✅ PII detection complete")
            
            # Step 4: Save results
            task4 = progress.add_task("Saving results...", total=None)
            
            # Create output directory
            output_path = Path(output_dir) / Path(file_path).stem
            output_path.mkdir(parents=True, exist_ok=True)
            
            # Save JSON
            json_file = output_path / "analysis.json"
            with open(json_file, 'w') as f:
                json.dump(analysis.dict(), f, indent=2, default=str)
            
            progress.update(task4, description="✅ Results saved")
        
        # Display results
        _display_results(analysis, str(json_file))
        
    except Exception as e:
        console.print(f"[red]Error processing document:[/red] {str(e)}")
        sys.exit(1)

def _display_results(analysis, output_file: str):
    """Display processing results in a formatted way."""
    
    # Summary panel
    summary_panel = Panel(
        analysis.summary,
        title="📄 Document Summary",
        border_style="blue"
    )
    console.print(summary_panel)
    
    # Results table
    table = Table(title="📊 Analysis Results")
    table.add_column("Field", style="cyan", no_wrap=True)
    table.add_column("Value", style="white")
    
    table.add_row("Document Type", analysis.document_type.value.title())
    table.add_row("Confidence", f"{analysis.confidence:.2%}")
    table.add_row("Processing Time", f"{analysis.processing_time:.2f}s")
    table.add_row("Model Used", analysis.model_used)
    table.add_row("Cost Estimate", f"${analysis.cost_estimate:.4f}" if analysis.cost_estimate else "N/A")
    table.add_row("Output File", output_file)
    
    console.print(table)
    
    # Extracted fields
    if analysis.extracted_fields:
        console.print("\n[bold yellow]📋 Extracted Fields:[/bold yellow]")
        fields_json = JSON(json.dumps(analysis.extracted_fields, indent=2, default=str))
        console.print(fields_json)

@cli.command()
@click.argument('directory', type=click.Path(exists=True))
@click.option('--model', default='gpt-4o', help='AI model to use')
@click.option('--output-dir', default='outputs', help='Output directory for results')
@click.option('--parallel', '-p', default=3, help='Number of parallel processes')
def batch(directory: str, model: str, output_dir: str, parallel: int):
    """Process multiple documents in a directory."""
    
    files = []
    for ext in settings.allowed_extensions:
        files.extend(Path(directory).glob(f"*.{ext}"))
    
    if not files:
        console.print(f"[yellow]No supported files found in {directory}[/yellow]")
        return
    
    console.print(f"[bold blue]Found {len(files)} files to process[/bold blue]")
    
    # Process files (simplified for demo)
    for file_path in files:
        console.print(f"Processing: {file_path.name}")
        try:
            asyncio.run(_process_document(str(file_path), model, output_dir, 'json', True, False))
        except Exception as e:
            console.print(f"[red]Failed to process {file_path.name}: {str(e)}[/red]")

@cli.command()
def config():
    """Show current configuration."""
    
    table = Table(title="⚙️ Configuration")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="white")
    
    table.add_row("Upload Directory", settings.upload_dir)
    table.add_row("Output Directory", settings.output_dir)
    table.add_row("Max File Size", f"{settings.max_file_size / 1024 / 1024:.1f} MB")
    table.add_row("Allowed Extensions", ", ".join(settings.allowed_extensions))
    table.add_row("OpenAI API Key", "✅ Configured" if settings.openai_api_key else "❌ Not configured")
    table.add_row("Anthropic API Key", "✅ Configured" if settings.anthropic_api_key else "❌ Not configured")
    
    console.print(table)

@cli.command()
@click.argument('file_path', type=click.Path(exists=True))
def validate(file_path: str):
    """Validate if a file can be processed."""
    
    parser = DocumentParser()
    
    try:
        text, metadata = parser.parse_file(file_path)
        
        console.print(f"[green]✅ File can be processed[/green]")
        console.print(f"[dim]File type: {metadata.mime_type}[/dim]")
        console.print(f"[dim]File size: {metadata.file_size / 1024:.1f} KB[/dim]")
        console.print(f"[dim]Text extracted: {len(text)} characters[/dim]")
        
        if len(text.strip()) == 0:
            console.print("[yellow]⚠️ No text could be extracted (OCR might be needed)[/yellow]")
        
    except Exception as e:
        console.print(f"[red]❌ File cannot be processed: {str(e)}[/red]")

if __name__ == '__main__':
    cli()