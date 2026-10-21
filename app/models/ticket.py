from app import db


class Ticket(db.Model):
    __tablename__ = "tickets"

    id = db.Column(
        db.Integer,
        db.Identity(always=True),
        primary_key=True
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False
    )

    subject = db.Column(db.String(160), nullable=False)

    description = db.Column(db.Text, nullable=False)

    priority = db.Column(
        db.String(10),
        nullable=False,
        server_default="normal"
    )

    status = db.Column(
        db.String(20),
        nullable=False,
        server_default="open"
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.func.now()
    )