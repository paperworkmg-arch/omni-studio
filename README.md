# Omni Studio

Unified production platform for Volt Records - combines audio AI tools, business automation, and AI agents into a single command center.

## Features

### Audio Production
- **StableDAW** - Browser-based AI audio DAW (text-to-audio, inpainting, LoRA training)
- **Stable Audio 3** - Text-to-audio generation for music and sound effects
- **TASCAR** - Spatial audio rendering for hearing research
- **ACE-Step** - Music generation (Suno alternative)

### Business Automation
- **CRM System** - Client management with lead tracking
- **Invoice Management** - Track and manage invoices
- **Content Calendar** - Social media scheduling and approvals
- **Approval Monitor** - Automated desktop notifications for pending approvals

### AI Agents
- **Hermes** - Personal AI agent with autonomous workflows
- **Email Agent** - Automated email responses
- **Outreach Agent** - LinkedIn/email outreach automation
- **Content Agent** - Social media content creation
- **CRM Agent** - Client relationship management
- **Invoice Agent** - Billing automation

## Quick Start

### Prerequisites

- Python 3.10+
- Node.js 18+
- Pinokio (for audio app management)

### Installation

1. Open Pinokio
2. Search for "Omni Studio"
3. Click Install
4. Click Start

### Manual Installation

```bash
# Clone the repository
git clone https://github.com/paperworkmg-arch/omni-studio.git
cd omni-studio

# Install dependencies
cd app/dashboard
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Install frontend
cd ../volt-dashboard
npm install
npm run build

# Start the dashboard
cd ../dashboard
python omni.py
```

The dashboard will be available at `http://127.0.0.1:8500`

## Architecture

```
omni-studio/
├── app/
│   ├── dashboard/              # Python FastAPI backend
│   │   ├── omni.py             # Main server
│   │   └── requirements.txt
│   ├── volt-dashboard/         # React frontend
│   │   ├── src/
│   │   └── package.json
│   ├── omni-source/            # Business automation suite
│   │   ├── agents/             # AI agents
│   │   ├── core/               # Business logic
│   │   ├── integrations/       # Third-party integrations
│   │   ├── scripts/            # Automation scripts
│   │   └── data/               # Databases and assets
│   ├── stable-audio-3/         # Stable Audio 3 (git submodule)
│   ├── stabledaw/              # StableDAW (git submodule)
│   └── tascar/                 # TASCAR (git submodule)
├── pinokio.js                  # Pinokio launcher UI
├── pinokio.json                # App metadata
├── install.js                  # Installation script
├── start.js                    # Launch script
├── approval_monitor.js         # Approval notification daemon
├── approval_manager.js         # Approval management CLI
└── README.md
```

## Approval System

The approval monitor runs automatically and sends desktop notifications for:
- Pending client approvals
- Pending invoice approvals
- Pending content approvals
- Agent workflow approvals

### Usage

1. **Start Monitor**: Click "Approval Monitor" in the sidebar
2. **View Approvals**: Click "List Pending Approvals" to see all items
3. **Approve/Reject**: Use the CLI to approve or reject items:
   ```bash
   python scripts/approval_manager.py list
   python scripts/approval_manager.py approve client 123
   python scripts/approval_manager.py reject invoice 456
   ```

## API Endpoints

### Core
- `GET /api/health` - System health check
- `GET /api/agents` - List AI agents
- `GET /api/tasks` - List tasks
- `GET /api/activity` - Activity feed

### Audio Apps
- `GET /api/audio-apps` - List all audio apps
- `POST /api/audio-apps/{id}/launch` - Launch an audio app
- `POST /api/audio-apps/{id}/stop` - Stop an audio app

### Catalog
- `GET /api/catalog/tracks` - List all tracks
- `GET /api/catalog/summary` - Catalog statistics

### Business
- `GET /api/clients` - List clients
- `GET /api/invoices` - List invoices
- `GET /api/content` - List content items

## Integrated Audio Apps

### StableDAW
- **Port**: 5173 (frontend), 8600 (backend)
- **Features**: MAKE, EDIT, MIX, DJ/VJ, TRAIN, LEARN

### Stable Audio 3
- **Port**: Dynamic (Gradio)
- **Models**: Small Music, Small SFX, Medium

### TASCAR
- **Type**: CLI tool (no web UI)
- **Use case**: Spatial audio rendering

### ACE-Step
- **Type**: Gradio web UI
- **Use case**: Music generation

## Environment Variables

Copy `.env.example` to `.env` and configure:
- `GOOGLE_API_KEY` - Google AI API key
- `KIMI_API_KEY` - Kimi AI API key
- `XAI_API_KEY` - xAI API key
- `OPENROUTER_API_KEY` - OpenRouter API key
- `SUNO_API_KEY` - Suno API key
- `SMTP_USERNAME` / `SMTP_PASSWORD` - Email credentials

## Development

```bash
# Start frontend dev server
cd app/volt-dashboard
npm run dev

# Start backend server
cd app/dashboard
python omni.py
```

## License

MIT License - Volt Records

## Credits

- [StableDAW](https://github.com/gantasmo/stabledaw) by GANTASMO
- [Stable Audio 3](https://github.com/Stability-AI/stable-audio-3) by Stability AI
- [TASCAR](https://github.com/gisogrimm/tascar) by GISOGrimm
- [ACE-Step](https://github.com/ace-step/ACE-Step) by ACE-Step
