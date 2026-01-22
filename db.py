import os
from typing import Optional, Dict
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import StaticPool

# Base class for models (shared)
Base = declarative_base()

# Module-level placeholders (set by init_db)
engine = None
SessionLocal = None

# Multi-database support: store multiple engines and sessionmakers
_databases: Dict[str, Dict] = {}


def init_db(database_url: Optional[str] = None):
    """Initialize the SQLAlchemy engine and session factory.

    If database_url is not provided, the function will read
    DATABASE_URL or DB_BACKEND from the environment and choose a default.
    Creates all tables defined in models.
    Returns the created engine.
    
    Supports any SQLAlchemy-compatible database via:
    1. DATABASE_URL environment variable (e.g., mysql://user:pass@host/db)
    2. DB_BACKEND environment variable (sqlite/postgres/postgresql)
    3. Direct database_url parameter
    
    Examples:
        - DATABASE_URL=mysql+pymysql://user:pass@localhost/invoices
        - DATABASE_URL=oracle+cx_oracle://user:pass@localhost/db
        - DATABASE_URL=mssql+pyodbc://user:pass@localhost/db
    """
    global engine, SessionLocal

    # First, check if DATABASE_URL is provided (supports any database)
    env_database_url = os.getenv("DATABASE_URL")
    
    if database_url is None:
        if env_database_url:
            # Use DATABASE_URL if provided (supports any SQLAlchemy database)
            database_url = env_database_url
            # For non-SQLite databases, use default connection args
            if database_url.startswith("sqlite"):
                connect_args = {"check_same_thread": False}
                if ":memory:" in database_url:
                    poolclass = StaticPool
                else:
                    poolclass = None
            else:
                connect_args = {}
                poolclass = None
        else:
            # Fall back to DB_BACKEND for SQLite/PostgreSQL
            DB_BACKEND = os.getenv("DB_BACKEND", "sqlite")

            if DB_BACKEND == "postgres" or DB_BACKEND == "postgresql":
                # Read PostgreSQL connection parameters from environment
                PG_HOST = os.getenv('PG_HOST', 'localhost')
                PG_PORT = os.getenv('PG_PORT', '5432')
                PG_DATABASE = os.getenv('PG_DATABASE', 'invoices')
                PG_USER = os.getenv('PG_USER', 'postgres')
                PG_PASSWORD = os.getenv('PG_PASSWORD', '')
                database_url = f"postgresql://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DATABASE}"
                connect_args = {}
                poolclass = None
            else:
                DB_PATH = os.getenv('DB_PATH', 'invoices.db')
                database_url = f"sqlite:///./{DB_PATH}"
                connect_args = {"check_same_thread": False}
                poolclass = None
    else:
        # allow caller to override connect_args for sqlite in-memory tests
        if database_url.startswith("sqlite"):
            connect_args = {"check_same_thread": False}
            # Use StaticPool for in-memory databases to ensure connection reuse
            if ":memory:" in database_url:
                poolclass = StaticPool
            else:
                poolclass = None
        else:
            connect_args = {}
            poolclass = None

    engine = create_engine(
        database_url, 
        connect_args=connect_args,
        poolclass=poolclass
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    # Import all models to ensure they are registered with Base
    from models.invoice import Invoice, InvoiceConfidence
    from models.item import Item

    # Create all tables
    Base.metadata.create_all(bind=engine)

    # expose for imports
    globals()["engine"] = engine
    globals()["SessionLocal"] = SessionLocal
    return engine


def get_db():
    """FastAPI dependency generator that yields a DB session from the default database.

    Requires init_db() to have been called first.
    """
    if SessionLocal is None:
        # Lazily initialize with defaults if not already initialized
        init_db()

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_multi_db(primary_db_url: Optional[str] = None, **databases: str):
    """Initialize multiple databases simultaneously.
    
    Args:
        primary_db_url: URL for the primary/default database (can be None to use env vars)
        **databases: Additional named databases, e.g., analytics_db="postgresql://...",
                     cache_db="sqlite:///cache.db"
    
    Examples:
        init_multi_db(
            primary_db_url="sqlite:///./invoices.db",
            analytics_db="postgresql://user:pass@localhost/analytics",
            cache_db="sqlite:///./cache.db"
        )
    """
    global engine, SessionLocal, _databases
    
    # Initialize primary database
    if primary_db_url:
        engine = _create_engine_from_url(primary_db_url)
    else:
        # Use existing init_db logic for primary
        init_db()
        return  # If no additional databases, just use regular init_db
    
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    _databases['default'] = {
        'engine': engine,
        'SessionLocal': SessionLocal,
        'url': primary_db_url or os.getenv("DATABASE_URL")
    }
    
    # Initialize additional named databases
    for db_name, db_url in databases.items():
        db_engine = _create_engine_from_url(db_url)
        db_session_local = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)
        _databases[db_name] = {
            'engine': db_engine,
            'SessionLocal': db_session_local,
            'url': db_url
        }
        
        # Create tables on this database too (if models are registered)
        try:
            from models.invoice import Invoice, InvoiceConfidence
            from models.item import Item
            Base.metadata.create_all(bind=db_engine)
        except Exception:
            pass  # Some databases might not support all model features


def _create_engine_from_url(database_url: str):
    """Helper function to create an engine from a database URL."""
    if database_url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
        if ":memory:" in database_url:
            poolclass = StaticPool
        else:
            poolclass = None
    else:
        connect_args = {}
        poolclass = None
    
    return create_engine(
        database_url,
        connect_args=connect_args,
        poolclass=poolclass
    )


def get_db_by_name(db_name: str = 'default'):
    """FastAPI dependency generator that yields a DB session from a named database.
    
    Args:
        db_name: Name of the database (must be registered via init_multi_db)
    
    Returns:
        Generator that yields a database session
    
    Example:
        @app.get("/analytics")
        async def get_analytics(db: Session = Depends(get_db_by_name("analytics_db"))):
            # Use analytics database
            pass
    """
    if db_name not in _databases:
        raise ValueError(f"Database '{db_name}' not found. Available databases: {list(_databases.keys())}")
    
    SessionLocal_named = _databases[db_name]['SessionLocal']
    db = SessionLocal_named()
    try:
        yield db
    finally:
        db.close()


def list_databases() -> Dict[str, str]:
    """List all registered databases and their URLs.
    
    Returns:
        Dictionary mapping database names to their URLs
    """
    return {name: info['url'] for name, info in _databases.items()}


def get_database_info(db_name: str = 'default') -> Dict:
    """Get information about a specific database.
    
    Args:
        db_name: Name of the database
    
    Returns:
        Dictionary with engine, SessionLocal, and url
    """
    if db_name not in _databases:
        raise ValueError(f"Database '{db_name}' not found. Available databases: {list(_databases.keys())}")
    return _databases[db_name]
