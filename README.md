# FindIt 2.0 — Dedicated University Lost & Found Sentinel
### 🏆 Dual-Interface Enterprise Architecture (Member Portal + Admin Command Center)

**FindIt** is a next-generation campus lost and found ecosystem engineered with a strict two-tier architecture:
1. **Dedicated Member Dashboard**: A unified, distraction-free portal for **Students, Teachers, and Staff** to submit lost or found requests, track admin verification status, and claim recovered items.
2. **Dedicated Admin Command Center**: An executive administrative interface for **Campus Admins Only** to review and approve incoming item requests, decide ownership claims, and officially authorize physical item handovers ("Give Item").
3. **Strict Institution Privacy (No General Public)**: Unauthenticated visitors cannot browse student reports, item records, or campus data. Access is strictly gated behind verified campus authentication.

---

## 🏛️ Two-Tier Dedicated Architecture

### 1. 🎓 Member Workspace (Student · Teacher · Staff)
- **Role-Aware Workspaces**: Auto-branded views for Students, Faculty/Teachers, and Campus Staff.
- **Request Submission Hub**: 1-click submission for Lost and Found requests with image upload, categories, campus zones, and secret verification questions.
- **My Submitted Requests Tracking**: Real-time status badges:
  - `🟡 Pending Admin Approval`: Transparent notification that the request is under administrative review.
  - `🟢 Approved & Live`: Published to the verified campus noticeboard.
  - `🎉 Safely Handed Over`: Belongs to owner and marked resolved.
  - `🔴 Rejected`: Filtered or duplicate submission.
- **Verified Campus Feed**: Live, verified items approved by campus administrators.
- **Ownership Claims & Handover**: Submit ownership proofs and access official **Digital Handover Passes** upon approval.
- **Smart QR Tags**: Generate scannable QR tags for laptops, student IDs, and keys.

### 2. 👑 Admin Command Center (Admin Only)
- **Item Approvals Queue (`admin prove etc`)**: Review all item submissions from students, teachers, and staff. 1-click **Approve & Publish** or **Reject** with automated notifications.
- **Claims & Handover Desk (`give iteas`)**: Review claimant ownership proofs and answers to verification challenges. 1-click **Authorize Handover (Give Item)** to generate handover passes and mark cases resolved.
- **Telemetry & Hotspots**: Chart.js visual telemetry of incident categories and campus hotspot locations.
- **Audit Records Export**: 1-click CSV export of all campus lost and found incidents for university security archives.
- **Member Approvals**: Manage pending student and staff registrations.

### 3. 🔒 Strict Campus Privacy (No General Public)
- All item browsing, maps, and reports require active campus login.
- Unauthenticated visitors are automatically directed to the secure sign-in portal.

---

## 🔑 1-Click Demo & Hackathon Logins

Use the **"Judge Login"** dropdown in the navigation bar for instant 1-click access:

| Role | Name | Email | Password | Landing View |
|---|---|---|---|---|
| **Campus Admin** | Prof. Robert Sterling | `admin@apex.edu` | `password123` | **Admin Command Center** (`/admin/`) |
| **Student** | Sarah Jenkins | `student@apex.edu` | `password123` | **Student Workspace** (`/`) |
| **Teacher / Faculty** | Dr. Eleanor Vance | `teacher@apex.edu` | `password123` | **Teacher Workspace** (`/`) |
| **Staff / Security** | Officer Marcus Cole | `staff@apex.edu` | `password123` | **Staff Workspace** (`/`) |

---

## ⚡ Deployment to Vercel & MongoDB Atlas

### 1. MongoDB Atlas Setup
1. Create a free cluster on [MongoDB Atlas](https://www.mongodb.com/cloud/atlas).
2. Obtain your connection URI:
   ```
   mongodb+srv://<username>:<password>@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority
   ```
3. Set your environment variables:
   - `MONGO_URI`: Your MongoDB Atlas URI.
   - `MONGO_DB_NAME`: `findit`
   - `SECRET_KEY`: A long secure random string.

### 2. Vercel Deployment
1. Connect your GitHub repository to [Vercel](https://vercel.com).
2. Add your environment variables in Vercel Project Settings (`MONGO_URI`, `MONGO_DB_NAME`, `SECRET_KEY`).
3. Deploy! The project includes `vercel.json` and `api/index.py` configured for `@vercel/python` serverless deployment with `dnspython` support.

> **Resilient Local Fallback:** When running offline or without an active MongoDB connection, FindIt automatically falls back to an in-memory MongoMock engine pre-seeded with sample university workspaces, users, items, and pending approval queues.

---

## 💻 Local Run Instructions

```bash
# 1. Activate virtual environment
venv\Scripts\activate      # Windows
# or source venv/bin/activate on macOS/Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Launch application
python run.py
```
Open **http://127.0.0.1:5000** in your browser.
