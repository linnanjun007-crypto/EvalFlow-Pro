from app.db.base import Base
from app.db.session import engine
from app.models import *  # noqa: F401,F403


def main() -> None:
    Base.metadata.create_all(bind=engine)
    print("Database tables created successfully.")


if __name__ == "__main__":
    main()
