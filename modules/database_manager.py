# /modules/database_manager.py

import logging
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    BigInteger,
    UniqueConstraint,
    func
)
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.exc import IntegrityError

log = logging.getLogger(__name__)
Base = declarative_base()

class Counter(Base):
    __tablename__ = 'counters'
    id = Column(Integer, primary_key=True)
    guild_id = Column(BigInteger, nullable=False)
    group_name = Column(String, nullable=False)
    counter_name = Column(String, nullable=False)
    value = Column(Integer, nullable=False, default=0)
    __table_args__ = (UniqueConstraint('guild_id', 'group_name', 'counter_name', name='_guild_group_counter_uc'),)
    def __repr__(self): return f"<Counter(guild='{self.guild_id}', group='{self.group_name}', name='{self.counter_name}', value={self.value})>"

class ActiveView(Base):
    __tablename__ = 'active_views'
    message_id = Column(BigInteger, primary_key=True)
    channel_id = Column(BigInteger, nullable=False)
    guild_id = Column(BigInteger, nullable=False)
    group_name = Column(String, nullable=False)
    def __repr__(self): return f"<ActiveView(message_id='{self.message_id}', group_name='{self.group_name}')>"

class DatabaseManager:
    def __init__(self, db_file_path: str):
        self.db_file_path = db_file_path; self.engine = create_engine(f'sqlite:///{self.db_file_path}', echo=False); self.Session = sessionmaker(bind=self.engine)
        log.info(f"DatabaseManager initialized for file: {db_file_path}")

    def initialize_database(self):
        try: Base.metadata.create_all(self.engine); log.info("Database schema verified.")
        except Exception as e: log.critical(f"Failed to initialize database schema: {e}", exc_info=True); raise

    def _execute_transaction(self, func):
        session = self.Session()
        try: result = func(session); session.commit(); return result
        except Exception as e: session.rollback(); log.error(f"Database transaction failed: {e}", exc_info=True); raise
        finally: session.close()
    
    def create_counter(self, guild_id: int, group_name: str, counter_name: str):
        def transaction(session):
            if session.query(Counter).filter_by(guild_id=guild_id, group_name=group_name, counter_name=counter_name).first():
                return f"A counter named `{counter_name}` already exists in group `{group_name}`."
            session.add(Counter(guild_id=guild_id, group_name=group_name, counter_name=counter_name, value=0))
        return self._execute_transaction(transaction)

    def update_counter(self, guild_id: int, group_name: str, counter_name: str, action: str):
        def transaction(session):
            counter = session.query(Counter).filter_by(guild_id=guild_id, group_name=group_name, counter_name=counter_name).first()
            if counter:
                if action == 'inc': counter.value += 1
                elif action == 'dec': counter.value -= 1
        self._execute_transaction(transaction)

    def delete_counter(self, guild_id: int, group_name: str, counter_name: str):
        def transaction(session):
            counter = session.query(Counter).filter_by(guild_id=guild_id, group_name=group_name, counter_name=counter_name).first()
            if counter: session.delete(counter)
        self._execute_transaction(transaction)

    def delete_group(self, guild_id: int, group_name: str):
        def transaction(session):
            session.query(Counter).filter_by(guild_id=guild_id, group_name=group_name).delete()
            session.query(ActiveView).filter_by(guild_id=guild_id, group_name=group_name).delete()
            log.info(f"Queued full deletion for group '{group_name}' in guild '{guild_id}'.")
        self._execute_transaction(transaction)

    def get_counters_in_group(self, guild_id: int, group_name: str) -> list[dict]:
        def query(session):
            counters = session.query(Counter).filter_by(guild_id=guild_id, group_name=group_name).order_by(Counter.counter_name).all()
            return [{'name': c.counter_name, 'value': c.value} for c in counters]
        return self._execute_transaction(query)
    
    def get_all_groups(self, guild_id: int, group_filter: str = None) -> list[str]:
        def query(session):
            q = session.query(Counter.group_name).filter_by(guild_id=guild_id)
            if group_filter: q = q.filter_by(group_name=group_filter)
            return [row[0] for row in q.distinct().all()]
        return self._execute_transaction(query)
        
    def add_active_view(self, message_id: int, channel_id: int, guild_id: int, group_name: str):
        def transaction(session): session.merge(ActiveView(message_id=message_id, channel_id=channel_id, guild_id=guild_id, group_name=group_name))
        self._execute_transaction(transaction)

    def remove_active_view(self, message_id: int):
        def transaction(session):
            view = session.get(ActiveView, message_id)
            if view: session.delete(view)
        self._execute_transaction(transaction)

    def get_views_for_group(self, guild_id: int, group_name: str) -> list[dict]:
        def query(session):
            records = session.query(ActiveView).filter_by(guild_id=guild_id, group_name=group_name).all()
            return [{"message_id": r.message_id, "channel_id": r.channel_id, "guild_id": r.guild_id, "group_name": r.group_name} for r in records]
        return self._execute_transaction(query)

    def get_all_active_views(self) -> list[dict]:
        def query(session):
            records = session.query(ActiveView).all()
            return [
                {
                    "message_id": r.message_id,
                    "channel_id": r.channel_id,
                    "guild_id": r.guild_id,
                    "group_name": r.group_name
                }
                # --- THIS IS THE FIX: Changed 'record' to 'r' ---
                for r in records
            ]
        return self._execute_transaction(query)

    def is_group_empty(self, guild_id: int, group_name: str) -> bool:
        def query(session):
            count = session.query(func.count(Counter.id)).filter_by(guild_id=guild_id, group_name=group_name).scalar()
            return count == 0
        return self._execute_transaction(query)