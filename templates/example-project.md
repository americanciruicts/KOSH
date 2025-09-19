# Example Project: Todo API with AICoder

This example demonstrates how to use AICoder for AI-assisted development of a Todo API.

## 🚀 Quick Start

```bash
# 1. Initialize project
aicoder init

# 2. Start development session
aicoder start

# 3. Begin development with Claude Code
```

## 📁 Project Structure

```
todo-api/
├── CLAUDE.md                    # AI agent context
├── docs/
│   ├── README.md               # Project overview
│   ├── BRD.md                  # Business requirements
│   ├── TRD.md                  # Technical requirements
│   ├── TODO.md                 # Development tasks
│   ├── ARCHITECTURE.md         # System architecture
│   ├── TESTING.md              # Testing strategy
│   ├── DEPLOYMENT.md           # Deployment guide
│   └── CHANGELOG.md            # Version history
├── src/
│   ├── controllers/
│   ├── services/
│   ├── models/
│   └── middleware/
├── tests/
├── package.json
└── .aicoder/                   # Configuration
```

## 🎯 Development Workflow

### **1. Project Setup**
```bash
# Initialize with AICoder
aicoder init

# Edit CLAUDE.md with project details
# Update docs/README.md with overview
# Add tasks to docs/TODO.md
```

### **2. Development Session**
```bash
# Start session
aicoder start

# Claude Code will open with optimized prompt
# Begin development with AI assistance
```

### **3. Cost Management**
```bash
# Check costs
aicoder cost

# Compare model costs
aicoder model-compare 2000

# Enable batch API
aicoder batch enable
```

## 📋 Example Tasks

### **Task 1: Create User Model**
```bash
# In Claude Code, prompt:
"Create a User model with TypeScript interfaces, validation, and database schema"
```

### **Task 2: Implement Authentication**
```bash
# In Claude Code, prompt:
"Implement JWT authentication with login/register endpoints and middleware"
```

### **Task 3: Create Todo CRUD**
```bash
# In Claude Code, prompt:
"Create complete Todo CRUD operations: model, service, controller, and tests"
```

## 💰 Cost Optimization Examples

### **Efficient Prompting**
```typescript
// ✅ GOOD: Specific, batched request
"Create complete user management system with:
- User model with validation
- Authentication service with JWT
- User controller with CRUD operations
- Unit tests for all components
- API documentation"

// ❌ EXPENSIVE: Multiple separate requests
"Create user model" → "Create auth service" → "Create controller" → "Create tests"
```

### **Model Selection**
```bash
# For simple tasks (documentation, code review)
# Use Haiku model (80% cost savings)

# For development (features, debugging)
# Use Sonnet model (recommended)

# For complex logic (architecture decisions)
# Use Opus model (sparingly)
```

## 📚 Documentation Examples

### **CLAUDE.md Template**
```markdown
# AI Development Context

## 🎯 Project Overview
**Project**: Todo API
**Type**: REST API
**Language**: TypeScript
**Framework**: Express.js

## 🔧 Development Environment
**Package Manager**: npm
**Database**: PostgreSQL
**Deployment**: Docker + AWS

## 📋 Coding Standards
- Use TypeScript strict mode
- All functions must include error handling
- Write comprehensive tests for new features
- Follow existing architectural patterns
- Document all public APIs

## 🏗️ Architecture Patterns
- **Authentication**: JWT-based with refresh tokens
- **Database**: Repository pattern with TypeORM
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
- [ ] Implement user authentication
- [ ] Create Todo CRUD operations
- [ ] Add input validation
- [ ] Write comprehensive tests
- [ ] Set up CI/CD pipeline

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
```

### **TODO.md Example**
```markdown
# Development Tasks

## In Progress
- [ ] Set up project structure
- [ ] Configure TypeScript
- [ ] Set up database connection

## Completed
- [x] Initialize project with AICoder
- [x] Create CLAUDE.md
- [x] Set up documentation structure

## Backlog
- [ ] Implement user authentication
- [ ] Create Todo CRUD operations
- [ ] Add input validation
- [ ] Write comprehensive tests
- [ ] Set up CI/CD pipeline
- [ ] Add API documentation
- [ ] Implement rate limiting
- [ ] Add logging and monitoring
```

## 🎯 Best Practices

### **1. Session Management**
- Keep sessions under 15 interactions
- Batch related tasks together
- End sessions when switching contexts
- Use specific, actionable prompts

### **2. Documentation**
- Update TODO.md with completed tasks
- Document patterns in ARCHITECTURE.md
- Update CHANGELOG.md for releases
- Keep CLAUDE.md current

### **3. Cost Optimization**
- Use Haiku for simple tasks
- Use Sonnet for development
- Use Opus sparingly
- Enable batch API for non-urgent tasks
- Be specific in prompts

## 🚨 Common Mistakes

### **❌ Avoid These**
- Vague prompts like "make it better"
- Multiple small requests instead of batching
- Not reading documentation first
- Not updating TODO.md after completion
- Using Opus for simple tasks

### **✅ Do These Instead**
- Specific prompts like "fix authentication error in login endpoint"
- Batch related tasks together
- Read project docs before making changes
- Update documentation after each task
- Use appropriate model for task complexity

## 💡 Tips for Success

1. **Start with `aicoder init`** for every new project
2. **Edit CLAUDE.md** with your specific project details
3. **Use `aicoder start`** for development sessions
4. **Check costs regularly** with `aicoder cost`
5. **Batch related tasks** to reduce API calls
6. **Document everything** for future reference
7. **Follow the patterns** in the prompt template
8. **Keep sessions focused** and end when switching contexts

---

**This example shows how AICoder can streamline AI-assisted development while keeping costs under control.** 