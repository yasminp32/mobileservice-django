# Mobile Service Shop (Django + PostgreSQL)

Features:
- REST API with Django REST Framework
- PostgreSQL via `DATABASE_URL`
- Auto-assign **nearest Shop** (within `ASSIGN_RADIUS_KM`, default 25km) based on customer pincode
- Auto-assign an **available Technician** from that shop (and mark them busy)
- Simple endpoints to create Shops, Technicians, Complaints

## Quick Start

1) **Create and activate venv**
```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
```

2) **Install deps**
```bash
pip install -r requirements.txt
```

3) **Create `.env`** (copy from `.env.example`) and set your Postgres URL:
```
DATABASE_URL=postgresql://postgres:yourpassword@localhost:5432/mobileshopdb
SECRET_KEY=some-long-random-string
DEBUG=1
ASSIGN_RADIUS_KM=25
GEO_COUNTRY=IN
```

4) **Migrate**
```bash
python manage.py makemigrations
python manage.py migrate
```

5) **Run server**
```bash
python manage.py runserver
```

## API (no auth for simplicity)

- `POST /api/shops/`
```json
{ "name": "Malappuram Main", "pincode": "676505", "latitude": 11.041, "longitude": 76.081, "approved": true }
```

- `POST /api/technicians/`
```json
{ "name": "Anas", "phone": "9000000001", "shop": 1, "available": true }
```

- `POST /api/complaints/`  → auto-assigns shop+technician
```json
{ "customer_name": "Rahul", "customer_phone": "9876543210", "issue": "Screen broken", "pincode": "676505" }
```
Response includes `assigned_shop` and `assigned_technician` once assigned.

- `POST /api/technicians/{id}/set_available/`
```json
{ "available": true }
```

- `GET /api/ping/` → sanity check

**Notes**
- If a Shop lacks latitude/longitude, the system will try to geocode from its `pincode` (country default `IN`) using `pgeocode` and cache the result on the model.
- If no technician is available at the nearest shop, the complaint stays `Pending` until you free one (`set_available`).

## Admin
Create a superuser:
```bash
python manage.py createsuperuser
```
Open `/admin/` for CRUD in the browser.
