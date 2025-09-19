#!/bin/bash

# AICoder - AI Agent Development Toolkit
# Streamlined CLI tool for Claude Code development with cost optimization
# Usage: aicoder <command> [options]

VERSION="2.1.0"
CONFIG_DIR="$HOME/.aicoder"
PROMPT_FILE="$CONFIG_DIR/templates/prompt.md"
CLAUDE_MD_FILE="CLAUDE.md"
SESSION_LOG="$CONFIG_DIR/sessions.log"
COST_LOG="$CONFIG_DIR/costs.log"

# Colors and icons
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

ICON_SUCCESS="✅"
ICON_WARNING="⚠️"
ICON_ERROR="❌"
ICON_INFO="ℹ️"
ICON_ROCKET="🚀"
ICON_MONEY="💰"
ICON_DOCS="📚"
ICON_AI="🤖"

# Initialize configuration
init_config() {
    if [ ! -d "$CONFIG_DIR" ]; then
        echo -e "${CYAN}${ICON_INFO} Setting up AICoder configuration...${NC}"
        echo -e "${CYAN}   → Creating config directory: $CONFIG_DIR${NC}"
        mkdir -p "$CONFIG_DIR"
        mkdir -p "$CONFIG_DIR/templates"
        mkdir -p "$CONFIG_DIR/sessions"
        echo -e "${CYAN}   → Creating AI agent prompt template${NC}"
        create_default_prompt
        echo -e "${GREEN}${ICON_SUCCESS} AICoder configuration initialized${NC}"
        echo -e "${CYAN}   → Config stored in: $CONFIG_DIR${NC}"
    fi
}

# Create default AI agent prompt
create_default_prompt() {
    cat > "$PROMPT_FILE" << 'EOF'
# AI Agent Development Guidelines

## 🎯 **PRIMARY DIRECTIVE**
You are an expert senior full-stack developer AI agent. Write production-quality code, maintain comprehensive documentation, follow industry best practices, and deliver enterprise-grade solutions while **optimizing for cost efficiency**.

## 💰 **COST OPTIMIZATION PRINCIPLES**

### **🚨 ALWAYS FOLLOW THESE COST-SAVING RULES:**

#### **1. Context Efficiency**
- **Read Documentation First**: ALWAYS start by reading project docs
- **Minimal Context**: Only request relevant files, not entire codebase
- **Smart Filtering**: Focus on files directly related to the current task
- **Token Limit**: Keep context under 15,000 tokens per request

#### **2. Task Batching Strategy**
```typescript
// ✅ GOOD: Batch related tasks together
"Create complete user management system: model + service + controller + tests"

// ❌ EXPENSIVE: Individual requests
"Create user model" → "Create user service" → "Create user controller" → "Create tests"
```

#### **3. Cache-First Approach**
- **Check Patterns**: Look for similar implementations in existing code
- **Reuse Solutions**: Adapt existing patterns rather than creating from scratch
- **Document Patterns**: Add reusable patterns for future use

#### **4. Specific Prompts Only**
```typescript
// ✅ EFFICIENT: Specific, actionable prompts
"Fix authentication error in login endpoint - user gets 401 on valid credentials"

// ❌ EXPENSIVE: Vague prompts that require clarification
"Make the app better and add some features"
```

## 📚 **MANDATORY DOCUMENTATION STANDARDS**

### **Required Documentation Structure**
Every project MUST maintain this documentation structure:

```
/docs/
├── README.md           # Project Overview & Quick Start
├── BRD.md             # Business Requirements Document
├── TRD.md             # Technical Requirements Document
├── TODO.md            # Development Task Tracking
├── ARCHITECTURE.md    # System Architecture Documentation
├── DEPLOYMENT.md      # Deployment & DevOps Guide
├── TESTING.md         # Testing Strategy & Guidelines
└── CHANGELOG.md       # Version History & Changes
```

### **Documentation Rules**
1. **Always Read First**: Before any code changes, read project docs
2. **Always Update**: Every significant change must update relevant documentation
3. **Cost Awareness**: Document patterns for reuse to avoid regeneration costs
4. **Decision Tracking**: Record all architectural decisions and gotchas
5. **Future-Proof**: Write docs for developers who will join the project later

## 🏗️ **ARCHITECTURAL PRINCIPLES**

### **Code Quality Standards**
```typescript
// ALWAYS follow these patterns:

// 1. Type Safety First (Prevent costly debugging iterations)
interface User {
  id: string;
  email: string;
  role: 'admin' | 'user' | 'manager';
  createdAt: Date;
  updatedAt: Date;
}

// 2. Comprehensive Error Handling (Prevent runtime issues)
async function createUser(userData: CreateUserRequest): Promise<ApiResponse<User>> {
  try {
    // Input validation
    const validationResult = validateUserData(userData);
    if (!validationResult.isValid) {
      return { success: false, error: validationResult.errors };
    }
    
    const user = await userService.create(userData);
    
    logger.info('User created successfully', { 
      userId: user.id, 
      email: user.email 
    });
    
    return { success: true, data: user };
  } catch (error) {
    logger.error('User creation failed', { 
      error: error.message, 
      userData: { email: userData.email } 
    });
    
    return { 
      success: false, 
      error: { 
        code: 'USER_CREATION_FAILED',
        message: 'Unable to create user account' 
      } 
    };
  }
}

// 3. Consistent Response Format
interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: {
    code: string;
    message: string;
    details?: any;
  };
  meta?: {
    timestamp: string;
    requestId: string;
  };
}
```

### **Database Patterns**
```sql
-- Always include these patterns:

-- 1. Proper indexing for performance
CREATE INDEX CONCURRENTLY idx_users_email ON users(email);
CREATE INDEX CONCURRENTLY idx_projects_status_date ON projects(status, created_at DESC);

-- 2. Audit fields on all tables
CREATE TABLE entities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Business fields here
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by UUID REFERENCES users(id),
    updated_by UUID REFERENCES users(id),
    version INTEGER DEFAULT 1
);

-- 3. Soft delete pattern
ALTER TABLE entities ADD COLUMN deleted_at TIMESTAMP NULL;
CREATE INDEX idx_entities_not_deleted ON entities(id) WHERE deleted_at IS NULL;
```

### **API Design Standards**
```typescript
// RESTful API patterns with proper validation

@Controller('users')
export class UsersController {
  constructor(private usersService: UsersService) {}

  @Post()
  @UsePipes(new ValidationPipe({ transform: true }))
  async create(@Body() createUserDto: CreateUserDto): Promise<ApiResponse<User>> {
    const result = await this.usersService.create(createUserDto);
    return {
      success: true,
      data: result,
      meta: {
        timestamp: new Date().toISOString(),
        requestId: generateRequestId()
      }
    };
  }

  @Get(':id')
  async findOne(@Param('id') id: string): Promise<ApiResponse<User>> {
    const user = await this.usersService.findOne(id);
    if (!user) {
      throw new NotFoundException('User not found');
    }
    
    return {
      success: true,
      data: user,
      meta: {
        timestamp: new Date().toISOString(),
        requestId: generateRequestId()
      }
    };
  }
}
```

## 🚀 **DEVELOPMENT WORKFLOW**

### **1. Project Initialization**
```bash
# Initialize new project with AI agent
aicoder init

# Create CLAUDE.md for project context
aicoder claude-md init

# Set up documentation structure
aicoder docs init
```

### **2. Development Session**
```bash
# Start development session with cost tracking
aicoder start

# Check session status and costs
aicoder status

# End session and update docs
aicoder end
```

### **3. Cost Optimization**
```bash
# Analyze costs and get recommendations
aicoder cost

# Compare model costs
aicoder model-compare

# Enable batch API for savings
aicoder batch enable
```

## 🎯 **BEST PRACTICES**

### **Model Selection Guide**
- **Haiku**: Simple tasks, code review, documentation (80% cost savings)
- **Sonnet**: Development, debugging, feature implementation (recommended)
- **Opus**: Complex logic, architecture decisions (use sparingly)

### **Session Management**
- Keep sessions under 15 interactions
- Batch related tasks together
- Use specific, actionable prompts
- End sessions when switching contexts

### **Documentation Priority**
1. Update TODO.md with completed tasks
2. Document new patterns in ARCHITECTURE.md
3. Update CHANGELOG.md for releases
4. Keep README.md current

## 🚨 **IMPORTANT NOTES**
- Always run tests before committing
- Follow semantic versioning for releases
- Use feature branches for all changes
- Keep dependencies up to date
- Monitor costs regularly
- Document all breaking changes

## 💡 **DEVELOPMENT TIPS**
- Use TypeScript strict mode
- Implement proper error boundaries
- Cache frequently accessed data
- Monitor performance metrics
- Write comprehensive tests
- Follow existing code patterns
EOF
}

# Create CLAUDE.md file for project context
cmd_claude_md_init() {
    echo -e "${CYAN}${ICON_INFO} Creating CLAUDE.md for AI agent context...${NC}"
    echo -e "${CYAN}   → Purpose: Provides project context to AI agents${NC}"
    echo -e "${CYAN}   → Contains: Project overview, coding standards, architecture${NC}"
    
    if [ -f "$CLAUDE_MD_FILE" ]; then
        echo -e "${YELLOW}${ICON_WARNING} CLAUDE.md already exists in current directory${NC}"
        echo -e "${CYAN}   → Location: $(pwd)/$CLAUDE_MD_FILE${NC}"
        read -p "Overwrite existing file? (y/N): " overwrite
        [[ ! $overwrite =~ ^[Yy] ]] && return 1
    fi
    
    cat > "$CLAUDE_MD_FILE" << 'EOF'
# AI Development Context

## 🎯 Project Overview
**Project**: {{PROJECT_NAME}}
**Type**: {{PROJECT_TYPE}}
**Language**: {{PRIMARY_LANGUAGE}}
**Framework**: {{FRAMEWORK}}

## 🔧 Development Environment
**Package Manager**: {{PACKAGE_MANAGER}}
**Database**: {{DATABASE}}
**Deployment**: {{DEPLOYMENT_PLATFORM}}

## 📋 Coding Standards
- Use {{LANGUAGE_STYLE}} conventions
- All functions must include error handling
- Write comprehensive tests for new features
- Follow existing architectural patterns
- Document all public APIs

## 🏗️ Architecture Patterns
- **Authentication**: JWT-based with refresh tokens
- **Database**: Repository pattern with TypeORM/Prisma
- **API**: RESTful endpoints with proper HTTP status codes
- **Error Handling**: Centralized error middleware
- **Testing**: Unit tests (Jest) + Integration tests

## 🚀 Common Commands
```bash
npm run dev          # Start development server
npm run test         # Run test suite
npm run lint         # Check code style
npm run build        # Build for production
npm run deploy       # Deploy to staging/production
```

## 🎯 Current Sprint Goals
- {{CURRENT_GOALS}}

## 🚨 Important Notes
- Always run tests before committing
- Follow semantic versioning for releases
- Use feature branches for all changes
- Keep dependencies up to date

## 💡 Development Tips
- Use TypeScript strict mode
- Implement proper error boundaries
- Cache frequently accessed data
- Monitor performance metrics
EOF

    echo -e "${GREEN}${ICON_SUCCESS} Created CLAUDE.md in current directory${NC}"
    echo -e "${CYAN}   → Location: $(pwd)/$CLAUDE_MD_FILE${NC}"
    echo -e "${CYAN}   → Next step: Edit CLAUDE.md to customize for your project${NC}"
    echo -e "${CYAN}   → Replace {{PROJECT_NAME}}, {{PROJECT_TYPE}}, etc. with actual values${NC}"
}

# Initialize documentation structure
cmd_docs_init() {
    echo -e "${CYAN}${ICON_INFO} Creating documentation structure...${NC}"
    echo -e "${CYAN}   → Purpose: Provides templates for project documentation${NC}"
    echo -e "${CYAN}   → Creating directory: $(pwd)/docs/${NC}"
    mkdir -p docs
    
    # Create README.md
    cat > docs/README.md << 'EOF'
# Project Name

## Overview
Brief description of the project.

## Quick Start
```bash
npm install
npm run dev
```

## Development
- [BRD.md](BRD.md) - Business Requirements
- [TRD.md](TRD.md) - Technical Requirements
- [ARCHITECTURE.md](ARCHITECTURE.md) - System Architecture
- [TODO.md](TODO.md) - Development Tasks
- [TESTING.md](TESTING.md) - Testing Strategy
- [DEPLOYMENT.md](DEPLOYMENT.md) - Deployment Guide
EOF

    # Create TODO.md
    cat > docs/TODO.md << 'EOF'
# Development Tasks

## In Progress
- [ ] Task 1
- [ ] Task 2

## Completed
- [x] Initial setup

## Backlog
- [ ] Future task 1
- [ ] Future task 2
EOF

    # Create other documentation files
    echo -e "${CYAN}   → Creating documentation templates:${NC}"
    echo -e "${CYAN}     • BRD.md (Business Requirements Document)${NC}"
    echo -e "${CYAN}     • TRD.md (Technical Requirements Document)${NC}"
    echo -e "${CYAN}     • ARCHITECTURE.md (System Architecture)${NC}"
    echo -e "${CYAN}     • TESTING.md (Testing Strategy)${NC}"
    echo -e "${CYAN}     • DEPLOYMENT.md (Deployment Guide)${NC}"
    echo -e "${CYAN}     • CHANGELOG.md (Version History)${NC}"
    
    touch docs/BRD.md docs/TRD.md docs/ARCHITECTURE.md docs/TESTING.md docs/DEPLOYMENT.md docs/CHANGELOG.md
    
    echo -e "${GREEN}${ICON_SUCCESS} Documentation structure created${NC}"
    echo -e "${CYAN}   → Location: $(pwd)/docs/${NC}"
    echo -e "${CYAN}   → Next step: Fill in the documentation templates${NC}"
}

# Start development session
cmd_start() {
    echo -e "${CYAN}${ICON_AI} Starting AI development session...${NC}"
    echo -e "${CYAN}   → Purpose: Launch Claude CLI with optimized development prompt${NC}"
    echo -e "${CYAN}   → Working directory: $(pwd)${NC}"
    
    init_config
    
    # Load AI agent prompt
    if [ ! -f "$PROMPT_FILE" ]; then
        echo -e "${YELLOW}${ICON_WARNING} AI prompt template not found${NC}"
        echo -e "${CYAN}   → Expected location: $PROMPT_FILE${NC}"
        return 1
    fi

    echo -e "${CYAN}${ICON_AI} Loading AI agent prompt template...${NC}"
    echo -e "${CYAN}   → Source: $PROMPT_FILE${NC}"
    echo -e "${CYAN}   → Contains: Cost optimization rules, coding standards, best practices${NC}"
    echo ""
    cat "$PROMPT_FILE"

    # Copy to clipboard if available
    echo ""
    if command -v pbcopy &>/dev/null; then
        pbcopy < "$PROMPT_FILE"
        echo -e "${GREEN}${ICON_SUCCESS} Prompt copied to clipboard${NC}"
        echo -e "${CYAN}   → You can paste this in Claude CLI when it opens${NC}"
    else
        echo -e "${YELLOW}${ICON_WARNING} Clipboard not available (pbcopy not found)${NC}"
        echo -e "${CYAN}   → You'll need to manually copy the prompt above${NC}"
    fi

    # Log session start
    echo "$(date): Session started in $(pwd)" >> "$SESSION_LOG"
    echo -e "${CYAN}   → Session logged to: $SESSION_LOG${NC}"
    
    echo ""
    echo -e "${CYAN}${ICON_INFO} About to launch Claude CLI...${NC}"
    echo -e "${CYAN}   → The prompt above contains cost optimization rules${NC}"
    echo -e "${CYAN}   → It will help Claude understand your project context${NC}"
    read -p "Press Enter to continue..." _
    
    echo -e "${GREEN}${ICON_ROCKET} Launching Claude CLI...${NC}"
    claude "$@"
}

# Show cost analysis
cmd_cost() {
    echo -e "${BOLD}${CYAN}💰 Cost Analysis & Optimization${NC}"
    echo -e "${CYAN}   → Purpose: Monitor API costs and get optimization tips${NC}"
    echo -e "${CYAN}   → Cost log location: $COST_LOG${NC}"
    echo ""
    
    if [ -f "$COST_LOG" ]; then
        echo "Recent costs:"
        tail -10 "$COST_LOG"
    else
        echo "No cost data available yet."
    fi
    
    echo ""
    echo -e "${BOLD}${CYAN}💡 Cost Optimization Tips:${NC}"
    echo -e "${CYAN}   • Use Haiku for simple tasks (80% savings)${NC}"
    echo -e "${CYAN}     → Examples: code review, documentation, simple fixes${NC}"
    echo -e "${CYAN}   • Use Sonnet for development (recommended)${NC}"
    echo -e "${CYAN}     → Examples: feature implementation, debugging, refactoring${NC}"
    echo -e "${CYAN}   • Use Opus sparingly (most expensive)${NC}"
    echo -e "${CYAN}     → Examples: complex architecture decisions, advanced algorithms${NC}"
    echo -e "${CYAN}   • Batch related tasks together${NC}"
    echo -e "${CYAN}     → Example: 'Create user model + service + controller + tests'${NC}"
    echo -e "${CYAN}   • Keep sessions under 15 interactions${NC}"
    echo -e "${CYAN}     → Why: Context grows expensive with longer sessions${NC}"
    echo -e "${CYAN}   • Be specific in your prompts${NC}"
    echo -e "${CYAN}     → Avoids back-and-forth clarification (saves tokens)${NC}"
}

# Compare model costs
cmd_model_compare() {
    local tokens="${1:-1000}"
    
    echo -e "${BOLD}${CYAN}📊 Model Cost Comparison (${tokens} tokens)${NC}"
    echo -e "${CYAN}   → Purpose: Compare costs across Claude models for informed decisions${NC}"
    echo -e "${CYAN}   → Based on 2025 Claude API pricing${NC}"
    echo ""
    
    # 2025 Claude API pricing (per 1K tokens)
    local haiku_cost=$(echo "scale=4; $tokens * 0.0008" | bc -l 2>/dev/null || echo "0.0008")
    local sonnet_cost=$(echo "scale=4; $tokens * 0.003" | bc -l 2>/dev/null || echo "0.003")
    local opus_cost=$(echo "scale=4; $tokens * 0.015" | bc -l 2>/dev/null || echo "0.015")
    
    echo "┌─────────────┬──────────────┬─────────────────┐"
    echo "│ Model       │ Cost/Request │ Best Use Case   │"
    echo "├─────────────┼──────────────┼─────────────────┤"
    echo "│ Haiku       │ \$${haiku_cost}       │ Simple tasks    │"
    echo "│ Sonnet      │ \$${sonnet_cost}       │ Development     │"
    echo "│ Opus        │ \$${opus_cost}       │ Complex logic   │"
    echo "└─────────────┴──────────────┴─────────────────┘"
    echo ""
    echo -e "${BOLD}${CYAN}💡 Recommendations:${NC}"
    echo -e "${CYAN}   • Haiku: Perfect for code review, simple fixes, documentation${NC}"
    echo -e "${CYAN}   • Sonnet: Best balance of capability and cost for development${NC}"
    echo -e "${CYAN}   • Opus: Reserve for complex architecture decisions and algorithms${NC}"
    echo ""
    echo -e "${CYAN}   → For ${tokens} tokens, you save \$$(echo "scale=4; ${sonnet_cost} - ${haiku_cost}" | bc -l 2>/dev/null || echo "0.002") by using Haiku vs Sonnet${NC}"
    echo -e "${CYAN}   → For ${tokens} tokens, you save \$$(echo "scale=4; ${opus_cost} - ${sonnet_cost}" | bc -l 2>/dev/null || echo "0.012") by using Sonnet vs Opus${NC}"
}

# Enable batch API
cmd_batch_enable() {
    echo -e "${GREEN}${ICON_SUCCESS} Batch API configuration enabled${NC}"
    echo -e "${CYAN}${ICON_INFO} This can save up to 50% on API costs for non-urgent tasks${NC}"
    echo -e "${CYAN}   → Purpose: Process requests in batches rather than real-time${NC}"
    echo -e "${CYAN}   → Trade-off: Slower response time for significant cost savings${NC}"
    echo ""
    echo -e "${BOLD}${CYAN}📊 Batch API is best for:${NC}"
    echo -e "${CYAN}   • Code generation${NC} - Generate multiple functions/components"
    echo -e "${CYAN}   • Documentation writing${NC} - Create comprehensive docs"
    echo -e "${CYAN}   • Code review${NC} - Analyze multiple files for improvements"
    echo -e "${CYAN}   • Pattern analysis${NC} - Identify patterns across codebase"
    echo ""
    echo -e "${BOLD}${CYAN}⚠️ Not recommended for:${NC}"
    echo -e "${CYAN}   • Interactive debugging${NC} - Need immediate feedback"
    echo -e "${CYAN}   • Real-time development${NC} - Rapid iteration cycles"
    echo -e "${CYAN}   • Learning/exploration${NC} - Back-and-forth conversations"
}

# Show session status
cmd_status() {
    echo -e "${BOLD}${CYAN}📊 Session Status${NC}"
    echo ""
    
    if [ -f "/tmp/aicoder.session" ]; then
        echo -e "${GREEN}${ICON_SUCCESS} Session active${NC}"
        cat /tmp/aicoder.session
    else
        echo -e "${YELLOW}${ICON_WARNING} No active session${NC}"
    fi
    
    echo ""
    echo -e "${BOLD}Recent sessions:${NC}"
    if [ -f "$SESSION_LOG" ]; then
        tail -5 "$SESSION_LOG"
    else
        echo "No session history"
    fi
}

# End session
cmd_end() {
    if [ -f "/tmp/aicoder.session" ]; then
        rm /tmp/aicoder.session
        echo -e "${GREEN}${ICON_SUCCESS} Session ended${NC}"
    else
        echo -e "${YELLOW}${ICON_WARNING} No active session to end${NC}"
    fi
    
    echo "$(date): Session ended" >> "$SESSION_LOG"
}

# Initialize new project
cmd_init() {
    echo -e "${CYAN}${ICON_ROCKET} Initializing AI agent project...${NC}"
    echo -e "${CYAN}   → Purpose: Set up project structure for AI-assisted development${NC}"
    echo -e "${CYAN}   → Current directory: $(pwd)${NC}"
    echo -e "${CYAN}   → Will create: CLAUDE.md, docs/ folder, configuration${NC}"
    echo ""
    
    init_config
    
    echo -e "${GREEN}${ICON_SUCCESS} Setting up project structure...${NC}"
    
    # Create CLAUDE.md
    cmd_claude_md_init
    
    # Initialize documentation
    cmd_docs_init
    
    echo -e "${GREEN}${ICON_SUCCESS} AI agent project initialized successfully!${NC}"
    echo ""
    echo -e "${BOLD}${CYAN}📋 What was created:${NC}"
    echo -e "${CYAN}   • CLAUDE.md - AI agent context file${NC}"
    echo -e "${CYAN}   • docs/ - Documentation templates${NC}"
    echo -e "${CYAN}   • ~/.aicoder/ - Configuration and templates${NC}"
    echo ""
    echo -e "${BOLD}${CYAN}🚀 Next steps:${NC}"
    echo -e "${CYAN}   1. Edit CLAUDE.md with your project details${NC}"
    echo -e "${CYAN}      → Replace {{PROJECT_NAME}}, {{PROJECT_TYPE}}, etc.${NC}"
    echo -e "${CYAN}   2. Update docs/README.md with project overview${NC}"
    echo -e "${CYAN}   3. Add development tasks to docs/TODO.md${NC}"
    echo -e "${CYAN}   4. Run 'aicoder start' to begin AI-assisted development${NC}"
    echo ""
    echo -e "${BOLD}${CYAN}💡 Why this helps:${NC}"
    echo -e "${CYAN}   • AI agents will understand your project context${NC}"
    echo -e "${CYAN}   • Structured documentation improves AI responses${NC}"
    echo -e "${CYAN}   • Cost optimization rules reduce API usage${NC}"
}

# Show help
cmd_help() {
    echo -e "${BOLD}${CYAN}AICoder - AI Agent Development Toolkit v${VERSION}${NC}"
    echo ""
    echo "Usage: aicoder <command> [options]"
    echo ""
    echo -e "${BOLD}${CYAN}📋 Commands:${NC}"
    echo -e "${CYAN}  init              ${NC}Initialize new AI agent project"
    echo -e "${CYAN}                    ${NC}→ Creates CLAUDE.md, docs/ folder, configuration"
    echo -e "${CYAN}  start [args]      ${NC}Start development session with Claude CLI"
    echo -e "${CYAN}                    ${NC}→ Loads optimized prompt, copies to clipboard, launches Claude"
    echo -e "${CYAN}  status            ${NC}Show current session status and history"
    echo -e "${CYAN}  end               ${NC}End current development session"
    echo -e "${CYAN}  claude-md init    ${NC}Create CLAUDE.md for project context"
    echo -e "${CYAN}                    ${NC}→ Provides AI agents with project-specific information"
    echo -e "${CYAN}  docs init         ${NC}Initialize documentation structure"
    echo -e "${CYAN}                    ${NC}→ Creates BRD, TRD, ARCHITECTURE, etc. templates"
    echo -e "${CYAN}  cost              ${NC}Show cost analysis and optimization tips"
    echo -e "${CYAN}  model-compare     ${NC}Compare costs across Claude models (Haiku/Sonnet/Opus)"
    echo -e "${CYAN}  batch enable      ${NC}Enable batch API for 50% cost savings"
    echo -e "${CYAN}  help              ${NC}Show this detailed help message"
    echo ""
    echo -e "${BOLD}${CYAN}🚀 Examples:${NC}"
    echo -e "${CYAN}  aicoder init                    ${NC}# Initialize new project with AI templates"
    echo -e "${CYAN}  aicoder start                   ${NC}# Start development session with Claude CLI"
    echo -e "${CYAN}  aicoder cost                    ${NC}# Analyze costs and get optimization tips"
    echo -e "${CYAN}  aicoder model-compare 2000     ${NC}# Compare model costs for 2000 tokens"
    echo ""
    echo -e "${BOLD}${CYAN}💡 Typical Workflow:${NC}"
    echo -e "${CYAN}  1. ${NC}aicoder init          ${CYAN}# Set up project structure${NC}"
    echo -e "${CYAN}  2. ${NC}Edit CLAUDE.md        ${CYAN}# Customize project context${NC}"
    echo -e "${CYAN}  3. ${NC}aicoder start         ${CYAN}# Begin AI-assisted development${NC}"
    echo -e "${CYAN}  4. ${NC}aicoder cost          ${CYAN}# Monitor and optimize costs${NC}"
    echo ""
    echo -e "${CYAN}For more information, visit: https://github.com/your-repo/aicoder${NC}"
}

# Main command dispatcher
case "$1" in
    init) cmd_init ;;
    start) cmd_start "${@:2}" ;;
    status) cmd_status ;;
    end) cmd_end ;;
    "claude-md") 
        case "$2" in
            init) cmd_claude_md_init ;;
            *) echo "Usage: aicoder claude-md init" ;;
        esac
        ;;
    docs)
        case "$2" in
            init) cmd_docs_init ;;
            *) echo "Usage: aicoder docs init" ;;
        esac
        ;;
    cost) cmd_cost ;;
    "model-compare") cmd_model_compare "$2" ;;
    batch)
        case "$2" in
            enable) cmd_batch_enable ;;
            *) echo "Usage: aicoder batch enable" ;;
        esac
        ;;
    help|--help|-h) cmd_help ;;
    *) 
        echo -e "${RED}${ICON_ERROR} Unknown command: $1${NC}"
        echo "Run 'aicoder help' for usage information"
        exit 1
        ;;
esac
