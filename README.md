# FindIt 2.0 — Universal Multi-Tenant University Lost & Found Sentinel
### 🏆 International Hackathon Edition

**FindIt** is a next-generation, AI-assisted multi-tenant campus lost and found ecosystem designed to fulfill every requirement of a modern university finder, security desk, and student portal.

Zero university is hardcoded: each institution manages its own isolated workspace, categories, geospatial campus coordinates, security desk hotlines, and verification modes.

---

## 🚀 Key Innovations & Features

1. **🌐 University Finder & Campus Directory**
   - Global campus directory allowing students and visitors to search partner universities by country, city, or domain.
   - Live campus telemetry: recovery rate, active lost reports, and direct entrance into public campus exploration mode.

2. **🗺️ Interactive Campus Map (Leaflet.js Geospatial Telemetry)**
   - Dark-mode campus GIS map with animated pulsating markers:
     - 🔴 **Red Pulse**: Lost items
     - 🟢 **Green Pulse**: Found items
     - 🔵 **Blue Pin**: 24/7 Campus Security Lost & Found Desks
   - Clickable interactive popups with image previews and 1-click claim workflows.

3. **🤖 AI Smart Match 2.0 Engine**
   - Multi-factor correlation algorithm computing real-time match confidence (e.g. `96% Match!`).
   - Cross-evaluates token overlap, category alignment, geospatial location proximity, and temporal delta (days difference).
   - Instant in-app notification triggers when opposite reports are correlated.

4. **🏷️ FindIt Smart QR Tags (Preventative Protection)**
   - Students register custom digital tags (`FIT-APEX-8821`) for laptops, keys, backpacks, and water bottles.
   - Generates printable QR sticker sheets.
   - When scanned by any smartphone camera, finders can send an **anonymous recovery notification** without exposing personal phone numbers or emails.

5. **🖨️ 1-Click Printable Missing Item Poster**
   - Automatically generates print-ready campus notice board posters with high-visibility styling, reward badges, and auto-generated QR codes directly linking to the digital case.

6. **🛡️ Anti-Fraud & Safe Handover Workflow**
   - Reporters of found items can set **Secret Verification Questions** (e.g. *"What sticker is on the laptop?"*).
   - Authorizing a claim issues a **Cryptographic Digital Handover Pass** with QR code and voucher ID for campus security guards to verify before item release.

7. **📊 Admin Command Center & Visual Telemetry**
   - Interactive Chart.js analytics: Category Distribution (Donut Chart) and Campus Hotspot Locations (Bar Chart).
   - Member approval queue and 1-click CSV export of all campus incident reports.

---

## ⚡ Quick Start & Run Instructions

```bash
# 1. Activate virtual environment
venv\Scripts\activate      # Windows

# 2. Install dependencies
pip install -r requirements.txt

# 3. Launch application
python run.py
```

Then visit **http://127.0.0.1:5000** in your browser.

> **Note on Database Resiliency:** FindIt includes an automated zero-downtime MongoDB fallback. If local MongoDB is offline or running in sandboxed mode, FindIt seamlessly initializes an in-memory MongoMock engine pre-seeded with rich sample universities, items, smart tags, and analytics!

---

## 🔑 1-Click Hackathon Judge & Demo Logins

For rapid evaluation, the navigation bar includes a **"Judge Login"** menu with 1-click authentication:

| Role | Name | Email | Password |
|---|---|---|---|
| **Campus Admin** | Prof. Robert Sterling | `admin@apex.edu` | `password123` |
| **Student** | Sarah Jenkins | `sarah@apex.edu` | `password123` |
| **Security Staff** | Officer Marcus Cole | `marcus.security@apex.edu` | `password123` |

---

## 🏛️ Multi-Tenant Isolation Architecture

- **Strict Document Scoping**: Every collection (`reports`, `claims`, `tags`, `users`, `notifications`) is strictly partitioned by `university_id`.
- **Compound Unique Constraints**: Emails are unique per university (`university_id + email`), enabling students to maintain accounts across institutions without conflict.
- **Verification Modes**:
  - `open`: Instant student self-registration.
  - `email_domain`: Restricted to official university email domains (`@harvard.edu`, `@apex.edu`).
  - `admin_approval`: Registrations remain pending until vetted by campus security/admin.

---

## 📁 Project Architecture

```
findit/
├── app/
│   ├── __init__.py          # App factory, context loaders, global variables
│   ├── db.py                # MongoDB connection + MongoMock resilient engine + Seed data
│   ├── utils.py             # Smart Match 2.0, image storage, notifications, OID helper
│   ├── auth.py              # Campus registration, student sign-up, session auth
│   ├── main.py              # University Finder directory, home dashboard, demo logins
│   ├── reports.py           # Lost/Found CRUD, search filters, Leaflet map, print poster
│   ├── tags.py              # FindIt Smart QR Tag generation & public anonymous scan
│   ├── admin.py             # Command Center analytics, approvals, settings, CSV export
│   ├── notifications.py     # In-app real-time notification alerts
│   ├── static/
│   │   ├── css/style.css    # World-class cyberpunk/glassmorphism design system
│   │   └── uploads/         # Uploaded images
│   └── templates/           # Fully responsive modern Jinja2 templates
├── config.py                # Configuration and environment variables
├── requirements.txt         # Python package specifications
└── run.py                   # Application entrypoint
```
