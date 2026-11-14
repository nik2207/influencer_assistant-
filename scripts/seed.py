"""Create a demo account with sample data: python -m scripts.seed"""
from datetime import date, timedelta

from app import models
from app.db import Base, SessionLocal, engine
from app.security import hash_password
from app.services.tools import now_ist

Base.metadata.create_all(bind=engine)
db = SessionLocal()
if db.query(models.User).filter_by(email="demo@example.com").first():
    print("Demo user already exists: demo@example.com / demo12345")
    raise SystemExit
u = models.User(email="demo@example.com", password_hash=hash_password("demo12345"), name="Riya Patil",
                handle="@riyacreates", niche="beauty lifestyle travel", followers=84000,
                city="Navi Mumbai", language="en")
db.add(u)
db.commit()
today = date.today()
db.add_all([
    models.Deal(user_id=u.id, brand="Mamaearth", kind="barter", title="Haircare kit", value_inr=4500,
                deliverables="2 reels, 3 stories", status="product_received", due_date=today + timedelta(days=3)),
    models.Deal(user_id=u.id, brand="boAt", kind="paid", title="Earbuds launch", value_inr=35000,
                deliverables="1 reel", status="negotiating"),
    models.Deal(user_id=u.id, brand="Wakefit", kind="paid", title="Mattress review", value_inr=50000,
                deliverables="1 reel, 4 stories", status="payment_pending"),
])
n = now_ist().replace(minute=0, second=0, microsecond=0)
db.add_all([
    models.Event(user_id=u.id, title="Shoot at Bandra studio", start_at=n + timedelta(days=1, hours=2),
                 end_at=n + timedelta(days=1, hours=5), location="Bandra"),
    models.Event(user_id=u.id, title="Call with boAt team", start_at=n + timedelta(days=2, hours=1),
                 end_at=n + timedelta(days=2, hours=2)),
])
db.commit()
print("Created demo user: demo@example.com / demo12345")
