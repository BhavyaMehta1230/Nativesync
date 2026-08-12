from sqlalchemy import create_engine, Column, Integer, String, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker

engine = create_engine("sqlite:///zaps.db")
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()
class Server(Base):
    __tablename__ = "servers"
    id = Column(Integer, primary_key=True, index=True)
    guild_id = Column(String, unique=True)
    name = Column(String)
Base.metadata.create_all(bind=engine)