from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# 数据库 URL，这里使用 MySQL
DATABASE_URL = "mysql+mysqlconnector://root:Nzoth2015.@localhost/chat_db"

# 创建数据库引擎
engine = create_engine(DATABASE_URL, echo=True)

# 创建 Session 类
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 创建基类
Base = declarative_base()

# 获取数据库会话
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
