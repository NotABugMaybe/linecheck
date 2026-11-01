import os
os.environ.setdefault("SECRET_KEY","test-only-secret-key-at-least-32-characters")
os.environ.setdefault("DATABASE_URL","sqlite:///./test_linecheck.db")
from fastapi.testclient import TestClient
from app.main import app
from app.database import Base,engine
import pytest
from PIL import Image
import io

@pytest.fixture
def client():
    Base.metadata.drop_all(engine); Base.metadata.create_all(engine)
    with TestClient(app) as c: yield c
    Base.metadata.drop_all(engine)
def signup(c,email="a@example.com"):
    r=c.post('/api/v1/auth/register',json={'organization':'Factory A','email':email,'password':'change-me-please-123'}); assert r.status_code==200; return {'Authorization':f"Bearer {r.json()['access_token']}"}
def test_tenant_isolation_and_profile_lifecycle(client):
    a=signup(client); b=signup(client,'b@example.com')
    p=client.post('/api/v1/profiles',headers=a,json={'name':'Cap inspection','product':'Cap X','defects':['crack']}).json()
    assert client.get(f"/api/v1/profiles/{p['id']}/images",headers=b).status_code==404
    assert client.post(f"/api/v1/profiles/{p['id']}/suspend",headers=b).status_code==404
    assert client.post(f"/api/v1/profiles/{p['id']}/approve",headers=a).status_code==409
    assert client.patch(f"/api/v1/profiles/{p['id']}",headers=a,json={'variant':'blue'}).json()['state']=='draft'
def test_auth_roles_and_insufficient_training(client):
    a=signup(client); p=client.post('/api/v1/profiles',headers=a,json={'name':'Bolt','product':'B1'}).json()
    r=client.post(f"/api/v1/profiles/{p['id']}/train",headers=a); assert r.status_code==422
    assert client.get('/api/v1/audit').status_code==401
    assert client.get('/api/v1/profiles',headers=a).status_code==200
def test_upload_validation_and_unknown_inspection(client):
    a=signup(client); p=client.post('/api/v1/profiles',headers=a,json={'name':'Seal','product':'S1'}).json()
    bad=client.post(f"/api/v1/profiles/{p['id']}/images",headers=a,files={'file':('bad.png',b'not an image','image/png')}); assert bad.status_code==400
    buf=io.BytesIO(); Image.new('RGB',(16,16),'white').save(buf,format='PNG')
    r=client.post(f"/api/v1/profiles/{p['id']}/inspect",headers=a,files={'file':('part.png',buf.getvalue(),'image/png')}); assert r.status_code==200 and r.json()['result']=='needs_review'
    assert client.get('/api/v1/reviews',headers=a).json()[0]['result']=='needs_review'
    review=client.patch('/api/v1/reviews/1',headers=a,json={'corrected_result':'pass','note':'Human verified'}); assert review.status_code==200
    assert review.json()['original_result']=='needs_review'
