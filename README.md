# FIKA
### Intelligent Multimodal Route Navigation System for Public Transportation in Tanzania

**FIKA** is a mobile-first public transportation navigation system designed to help commuters navigate public transport networks more easily, starting with selected routes in **Arusha, Tanzania**.

The system combines public transport route data, pedestrian navigation, geospatial technologies, and intelligent journey planning to help passengers identify suitable vehicles, locate boarding points, understand transfers, and know when to alight.

> **Project status:** Under active development  
> **Project type:** Final-Year Engineering Project  
> **Initial deployment area:** Arusha, Tanzania

---

## 1. The Problem

Navigating public transportation in unfamiliar areas can be challenging, particularly for people who:

- Do not know which public transport vehicle serves their destination.
- Are unfamiliar with boarding and alighting points.
- Have difficulty identifying the correct vehicle or destination board.
- Need to transfer between multiple routes.
- Cannot easily estimate journey duration, fares, or walking distances.

FIKA aims to address these challenges through a unified, accessible, and intelligent navigation platform.

## 2. Project Objectives

The primary objective is to design and develop a multimodal navigation system that:

1. Provides public transport route and destination discovery.
2. Identifies suitable boarding and alighting points.
3. Supports multimodal journey planning, combining walking and public transport.
4. Recommends alternative journeys based on time, cost, walking distance, and transfers.
5. Provides GPS-assisted navigation and smart stop alerts.
6. Estimates journey duration and fares using available transport data.
7. Provides an administrative platform for managing and verifying transport information.

## 3. Key Features

### Passenger Mobile Application

- Search for destinations and nearby transport stops.
- View available public transport routes.
- Receive step-by-step journey instructions.
- Identify vehicles using route information and destination-board references.
- View estimated fares and journey durations.
- Receive alternative journey recommendations.
- Navigate to boarding points and final destinations.
- Receive GPS-based alerts when approaching an alighting point.
- Report incorrect or outdated transport information.

### Intelligent Journey Planning

FIKA combines pedestrian and public transport networks to generate feasible journeys.

Users will be able to compare journeys based on:

- Fastest journey.
- Cheapest journey.
- Least walking.
- Fewest transfers.

### Smart Stop Alert

The application uses the passenger's smartphone GPS location to monitor their progress during a journey.

It can notify passengers as they approach their intended alighting point through visual, audio, or vibration alerts.

**Note:** The initial system focuses on passenger-side GPS navigation. Live GPS tracking of public transport vehicles is outside the initial MVP scope.

### Administrative Dashboard

The web-based dashboard will allow authorized administrators to:

- Register and manage transport routes.
- Add and update boarding and alighting points.
- Manage route sequences and transfer connections.
- Manage vehicle variants and destination-board information.
- Upload vehicle illustrations.
- Manage fare information.
- Review passenger reports.
- Verify and maintain transport data.

## 4. Technology Stack

| Component | Technology |
|---|---|
| Mobile application | Flutter / Dart |
| Backend API | Python / FastAPI |
| Administrative dashboard | React / TypeScript / Vite |
| Database | PostgreSQL |
| Geospatial extension | PostGIS |
| Interactive maps | MapLibre |
| Map data | OpenStreetMap |
| Pedestrian routing | OSRM / Valhalla |
| Transit graph | Python / NetworkX |
| Routing algorithms | Dijkstra / A* |
| Machine learning | Scikit-learn / XGBoost |
| API documentation | FastAPI / OpenAPI |
| Version control | Git / GitHub |

## 5. System Architecture

FIKA follows a modular client-server architecture.

```text
             ┌──────────────────────┐
             │   Passenger App      │
             │   Flutter / Dart     │
             └──────────┬───────────┘
                        │
                        │ REST API
                        │
             ┌──────────▼───────────┐
             │    FastAPI Backend   │
             │                      │
             │  Journey Planning    │
             │  Transit Routing     │
             │  Fare Estimation     │
             │  Smart Stop Logic    │
             │  ML Predictions      │
             └──────────┬───────────┘
                        │
             ┌──────────▼───────────┐
             │ PostgreSQL + PostGIS │
             │                      │
             │ Routes and Stops     │
             │ Transfers and Fares  │
             │ Journey Observations│
             │ Geographic Data     │
             └──────────────────────┘

             ┌──────────────────────┐
             │ Admin Dashboard      │
             │ React / TypeScript   │
             └──────────┬───────────┘
                        │
                        └── REST API
```

The backend is designed as a modular monolith for the initial implementation, keeping development and deployment manageable while allowing individual system components to evolve independently.

## 6. Repository Structure

```text
fika/
│
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── database.py
│   │   └── models.py
│   ├── migrations/
│   ├── tests/
│   └── requirements.txt
│
├── mobile/
│   └── # Flutter passenger application
│
├── admin/
│   └── # React administrative dashboard
│
├── data/
│   ├── raw/
│   ├── processed/
│   └── documentation/
│
├── docs/
│   ├── architecture/
│   ├── database/
│   └── fieldwork/
│
├── assets/
│   ├── vehicles/
│   ├── icons/
│   └── branding/
│
└── README.md
```

## 7. Local Development Setup

### Prerequisites

Install the following:

- Python 3.11 or later
- PostgreSQL
- PostGIS
- Git

Flutter and Node.js will also be required when setting up the mobile application and administrative dashboard.

### Clone the Repository

```bash
git clone https://github.com/YOUR-USERNAME/fika.git
cd fika
```

### Backend Setup

Navigate to the backend directory:

```bash
cd backend
```

Create a virtual environment:

```bash
python -m venv .venv
```

Activate it on Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Create a `.env` file inside the `backend` directory:

```env
DATABASE_URL=postgresql+psycopg://USERNAME:PASSWORD@localhost:5432/fika_db
```

Create a PostgreSQL database named `fika_db` and enable PostGIS:

```sql
CREATE EXTENSION IF NOT EXISTS postgis;
```

Apply database migrations:

```bash
alembic upgrade head
```

Start the development server:

```bash
uvicorn app.main:app --reload
```

The API will be available at:

- API: http://127.0.0.1:8000
- Interactive API documentation: http://127.0.0.1:8000/docs
- Health check: http://127.0.0.1:8000/health

## 8. Development Roadmap

| Phase | Development Focus | Status |
|---|---|---|
| 1 | Project foundation and environment setup | In progress |
| 2 | Database design and geospatial integration | In progress |
| 3 | Transport data management and administration | Planned |
| 4 | Multimodal routing engine | Planned |
| 5 | Journey planning API | Planned |
| 6 | Flutter passenger application | Planned |
| 7 | GPS navigation and Smart Stop Alert | Planned |
| 8 | Intelligence, testing, and field validation | Planned |

## 9. Research and Evaluation

The system will be evaluated using selected public transport routes in Arusha.

Planned evaluation areas include:

- Accuracy of route and stop information.
- Feasibility of recommended journeys.
- Accuracy of boarding, alighting, and transfer instructions.
- Fare estimation accuracy.
- Journey time estimation performance.
- Smart Stop Alert reliability.
- Application usability and API performance.

Machine learning will be introduced where sufficient real-world journey observations are available. A historical-average baseline will be used for comparison.

## 10. Data Sources and Acknowledgements

- [OpenStreetMap](https://www.openstreetmap.org/) — geographic and road network data.
- [PostGIS](https://postgis.net/) — geospatial database functionality.
- [MapLibre](https://maplibre.org/) — interactive mapping technology.
- [FastAPI](https://fastapi.tiangolo.com/) — backend API framework.
- [Flutter](https://flutter.dev/) — cross-platform mobile development.

Transport route, fare, and stop information will require local data collection and verification.

## 11. Project Scope and Limitations

The initial implementation is a research and development MVP focused on selected routes in Arusha.

It does not initially promise:

- Nationwide public transport coverage.
- Live vehicle tracking.
- Guaranteed real-time arrival predictions.
- Complete or universally verified fare information.

The accuracy and coverage of journey recommendations will depend on the availability and verification of transport network data.

## 12. License

License to be determined.

---

**FIKA — Helping you find your way.** 🇹🇿

*Designed and developed as an engineering project focused on making public transportation easier to understand and navigate in Tanzania.*
