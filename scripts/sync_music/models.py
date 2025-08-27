from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Float, Table, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()

playlist_track_association = Table(
    'playlist_tracks',
    Base.metadata,
    Column('playlist_id', Integer, ForeignKey('playlists.id')),
    Column('track_id', Integer, ForeignKey('tracks.id')),
    Column('position', Integer, default=0)
)

class Playlist(Base):
    __tablename__ = 'playlists'
    
    id = Column(Integer, primary_key=True)
    netease_id = Column(Integer, unique=True, nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text)
    creator_id = Column(Integer)
    creator_name = Column(String)
    track_count = Column(Integer, default=0)
    create_time = Column(DateTime)
    update_time = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    cover_img_url = Column(String)
    track_ids_hash = Column(String)  # 用于频率控制
    
    tracks = relationship("Track", secondary=playlist_track_association, back_populates="playlists")

class Track(Base):
    __tablename__ = 'tracks'
    
    id = Column(Integer, primary_key=True)
    netease_id = Column(Integer, unique=True, nullable=False)
    name = Column(String, nullable=False)
    duration = Column(Integer)
    artist_names = Column(String)
    bitrate = Column(Integer, nullable=True)
    file_hash = Column(String, nullable=True)
    file_path = Column(String, nullable=True)
    file_exists = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    playlists = relationship("Playlist", secondary=playlist_track_association, back_populates="tracks")