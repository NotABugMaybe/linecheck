from contextlib import asynccontextmanager
from pathlib import Path
import hashlib, uuid, io, logging
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import select
from PIL import Image, UnidentifiedImageError
from .database import Base, engine
from .config import settings
from .models import Organization, User, Site, Profile, ImageRecord, ModelVersion, AuditEvent, Inspection
from .schemas import Login, Register, ProfileCreate, ProfileUpdate, LabelUpdate, ReviewUpdate
from .security import get_db, current_user, require_roles, hash_password, verify_password, create_token

logging.basicConfig(level=logging.INFO, format='%(message)s')
@asynccontextmanager
async def lifespan(app):
    Base.metadata.create_all(bind=engine)
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    yield
app=FastAPI(title="LineCheck API", version="1.0.0", openapi_url="/api/v1/openapi.json", docs_url="/api/v1/docs", lifespan=lifespan)
@app.middleware("http")
async def request_context(request: Request, call_next):
    request.state.request_id=request.headers.get("X-Request-ID",str(uuid.uuid4()))
    response=await call_next(request); response.headers["X-Request-ID"]=request.state.request_id; return response
@app.get("/health")
def health(): return {"status":"ok"}
@app.get("/ready")
def ready(db: Session=Depends(get_db)):
    try: db.execute(select(1)); return {"status":"ready"}
    except Exception: raise HTTPException(503,"Database unavailable")
@app.post("/api/v1/auth/register")
def register(data: Register, db: Session=Depends(get_db)):
    if not settings.development_mode: raise HTTPException(404,"Not found")
    if db.scalar(select(User).where(User.email==data.email)): raise HTTPException(409,"Email already registered")
    org=Organization(name=data.organization); db.add(org); db.flush()
    user=User(organization_id=org.id,email=data.email,password_hash=hash_password(data.password),role="org_admin")
    db.add(user); db.commit(); db.refresh(user)
    return {"access_token":create_token(user),"token_type":"bearer","role":user.role,"organization_id":org.id}
@app.post("/api/v1/auth/login")
def login(data: Login, db: Session=Depends(get_db)):
    user=db.scalar(select(User).where(User.email==data.email))
    if not user or not verify_password(data.password,user.password_hash): raise HTTPException(401,"Invalid credentials")
    return {"access_token":create_token(user),"token_type":"bearer","role":user.role}
def audit(db,user,action,entity,entity_id,detail=""):
    db.add(AuditEvent(organization_id=user.organization_id,actor_id=user.id,action=action,entity_type=entity,entity_id=str(entity_id),detail=detail))
def scoped(db, model, ident, org_id):
    row=db.scalar(select(model).where(model.id==ident,model.organization_id==org_id))
    if not row: raise HTTPException(404,"Not found")
    return row
@app.get("/api/v1/me")
def me(user: User=Depends(current_user)): return {"id":user.id,"email":user.email,"role":user.role,"organization_id":user.organization_id}
@app.get("/api/v1/sites")
def list_sites(db: Session=Depends(get_db),user: User=Depends(current_user)):
    return db.scalars(select(Site).where(Site.organization_id==user.organization_id)).all()
@app.post("/api/v1/sites")
def create_site(data: dict, db: Session=Depends(get_db),user: User=Depends(require_roles("org_admin","quality_manager"))):
    site=Site(organization_id=user.organization_id,name=str(data.get("name",""))[:180],location=str(data.get("location",""))[:255]); db.add(site); db.flush(); audit(db,user,"site.create","site",site.id); db.commit(); return {"id":site.id,"name":site.name,"location":site.location}
@app.get("/api/v1/profiles")
def profiles(db: Session=Depends(get_db),user: User=Depends(current_user)):
    return db.scalars(select(Profile).where(Profile.organization_id==user.organization_id).order_by(Profile.id.desc())).all()
@app.post("/api/v1/profiles")
def create_profile(data: ProfileCreate,db: Session=Depends(get_db),user: User=Depends(require_roles("org_admin","quality_manager","engineer"))):
    p=Profile(organization_id=user.organization_id,**data.model_dump()); db.add(p); db.flush(); audit(db,user,"profile.create","profile",p.id); db.commit(); db.refresh(p); return p
@app.patch("/api/v1/profiles/{profile_id}")
def update_profile(profile_id:int,data:ProfileUpdate,db:Session=Depends(get_db),user:User=Depends(require_roles("org_admin","quality_manager","engineer"))):
    p=scoped(db,Profile,profile_id,user.organization_id)
    changed=False
    for key,value in data.model_dump(exclude_unset=True).items():
        if value is not None and getattr(p,key)!=value: setattr(p,key,value); changed=True
    if changed:
        p.config_version+=1
        if p.state in ("approved","needs_validation"): p.state="needs_validation"
        audit(db,user,"profile.update","profile",p.id,"Configuration changed; revalidation required")
    db.commit(); db.refresh(p); return p
@app.post("/api/v1/profiles/{profile_id}/clone")
def clone_profile(profile_id:int,db:Session=Depends(get_db),user:User=Depends(require_roles("org_admin","quality_manager","engineer"))):
    p=scoped(db,Profile,profile_id,user.organization_id); copy=Profile(organization_id=user.organization_id,name=p.name+" copy",product=p.product,variant=p.variant,defects=p.defects,capture=p.capture,thresholds=p.thresholds,state="draft"); db.add(copy); db.flush(); audit(db,user,"profile.clone","profile",copy.id); db.commit(); db.refresh(copy); return copy
@app.post("/api/v1/profiles/{profile_id}/approve")
def approve_profile(profile_id:int,db:Session=Depends(get_db),user:User=Depends(require_roles("org_admin","quality_manager"))):
    p=scoped(db,Profile,profile_id,user.organization_id)
    approved=db.scalar(select(ModelVersion).where(ModelVersion.profile_id==p.id,ModelVersion.organization_id==user.organization_id,ModelVersion.state=="candidate"))
    if not approved or p.state not in ("needs_validation","collecting_data","training"): raise HTTPException(409,"A candidate model and validation-ready profile are required")
    approved.state="approved"; p.state="approved"; p.approved_by=user.id; audit(db,user,"profile.approve","profile",p.id); db.commit(); return {"state":p.state,"model_version":approved.version}
@app.post("/api/v1/profiles/{profile_id}/suspend")
def suspend_profile(profile_id:int,db:Session=Depends(get_db),user:User=Depends(require_roles("org_admin","quality_manager"))):
    p=scoped(db,Profile,profile_id,user.organization_id); p.state="suspended"; audit(db,user,"profile.suspend","profile",p.id); db.commit(); return {"state":p.state}
@app.post("/api/v1/profiles/{profile_id}/images")
async def upload_image(profile_id:int,file:UploadFile=File(...),db:Session=Depends(get_db),user:User=Depends(current_user)):
    p=scoped(db,Profile,profile_id,user.organization_id); raw=await file.read(settings.max_upload_bytes+1)
    if len(raw)>settings.max_upload_bytes: raise HTTPException(413,"Image exceeds size limit")
    if file.content_type not in ("image/jpeg","image/png","image/webp","image/tiff"): raise HTTPException(415,"Unsupported image type")
    try:
        im=Image.open(io.BytesIO(raw)); im.verify(); im=Image.open(io.BytesIO(raw))
        if im.width<1 or im.height<1 or im.width*im.height>40_000_000: raise ValueError()
        fmt=im.format.lower()
        if fmt not in ("jpeg","png","webp","tiff"): raise ValueError()
    except (UnidentifiedImageError, OSError, ValueError): raise HTTPException(400,"Invalid or unsafe image")
    digest=hashlib.sha256(raw).hexdigest()
    exists=db.scalar(select(ImageRecord).where(ImageRecord.organization_id==user.organization_id,ImageRecord.profile_id==p.id,ImageRecord.sha256==digest))
    if exists: return {"id":exists.id,"sha256":digest,"duplicate":True}
    dest=settings.storage_dir/str(user.organization_id)/str(p.id); dest.mkdir(parents=True,exist_ok=True); path=dest/(digest+"."+fmt); path.write_bytes(raw)
    rec=ImageRecord(organization_id=user.organization_id,profile_id=p.id,path=str(path),sha256=digest); db.add(rec)
    if p.state=="draft": p.state="collecting_data"
    audit(db,user,"image.upload","image",digest); db.commit(); db.refresh(rec); return {"id":rec.id,"sha256":digest,"width":im.width,"height":im.height,"duplicate":False}
@app.get("/api/v1/profiles/{profile_id}/images")
def images(profile_id:int,db:Session=Depends(get_db),user:User=Depends(current_user)):
    scoped(db,Profile,profile_id,user.organization_id)
    return db.scalars(select(ImageRecord).where(ImageRecord.organization_id==user.organization_id,ImageRecord.profile_id==profile_id).order_by(ImageRecord.id.desc())).all()
@app.patch("/api/v1/images/{image_id}/label")
def label_image(image_id:int,data:LabelUpdate,db:Session=Depends(get_db),user:User=Depends(require_roles("org_admin","quality_manager","engineer","operator"))):
    rec=scoped(db,ImageRecord,image_id,user.organization_id); rec.label=data.label
    if data.split: rec.split=data.split
    audit(db,user,"image.label","image",rec.id,data.label); db.commit(); return {"id":rec.id,"label":rec.label,"split":rec.split,"reviewer":user.id}
@app.post("/api/v1/profiles/{profile_id}/train")
def train(profile_id:int,db:Session=Depends(get_db),user:User=Depends(require_roles("org_admin","quality_manager","engineer"))):
    p=scoped(db,Profile,profile_id,user.organization_id)
    rows=db.scalars(select(ImageRecord).where(ImageRecord.organization_id==user.organization_id,ImageRecord.profile_id==p.id)).all()
    labeled=[x for x in rows if x.label in ("good","defect")]
    splits={s:sum(1 for x in labeled if x.split==s) for s in ("train","validation","test")}
    if splits["train"]<10 or not splits["validation"] or not splits["test"]: raise HTTPException(422,{"error":"insufficient_data","message":"Need at least 10 labeled training images and non-empty validation and test splits","counts":splits})
    hashes={s:{x.sha256 for x in labeled if x.split==s} for s in splits}
    if (hashes["train"]&hashes["validation"]) or (hashes["train"]&hashes["test"]) or (hashes["validation"]&hashes["test"]): raise HTTPException(422,"Dataset leakage across splits")
    version=(db.scalar(select(ModelVersion.version).where(ModelVersion.profile_id==p.id).order_by(ModelVersion.version.desc()).limit(1)) or 0)+1
    mv=ModelVersion(organization_id=user.organization_id,profile_id=p.id,version=version,state="draft",dataset_version=hashlib.sha256("".join(sorted(x.sha256 for x in labeled)).encode()).hexdigest()[:16],config={"method":"documented-baseline-v1","seed":42,"splits":splits},metrics={})
    db.add(mv); p.state="training"; audit(db,user,"training.request","profile",p.id,f"version {version}; queued local baseline job"); db.commit(); return {"job_id":f"train-{mv.id}","status":"queued","model_version":version,"note":"Training is deliberately not simulated: this release gate awaits an installed, validated training worker."}
@app.get("/api/v1/models")
def models(db:Session=Depends(get_db),user:User=Depends(current_user)):
    return db.scalars(select(ModelVersion).where(ModelVersion.organization_id==user.organization_id).order_by(ModelVersion.id.desc())).all()
@app.post("/api/v1/profiles/{profile_id}/inspect")
async def inspect(profile_id:int,file:UploadFile=File(...),db:Session=Depends(get_db),user:User=Depends(current_user)):
    p=scoped(db,Profile,profile_id,user.organization_id)
    raw=await file.read(settings.max_upload_bytes+1)
    if len(raw)>settings.max_upload_bytes: raise HTTPException(413,"Image exceeds size limit")
    if file.content_type not in ("image/jpeg","image/png","image/webp","image/tiff"): raise HTTPException(415,"Unsupported image type")
    try:
        im=Image.open(io.BytesIO(raw)); im.verify(); im=Image.open(io.BytesIO(raw))
        if im.width<1 or im.height<1 or im.width*im.height>40_000_000: raise ValueError()
        if im.format.lower() not in ("jpeg","png","webp","tiff"): raise ValueError()
    except (UnidentifiedImageError, OSError, ValueError): raise HTTPException(400,"Invalid or unsafe image")
    if p.state!="approved": result="needs_review"; why="Profile is not approved for production inference"
    else: result="unknown"; why="No validated inference runtime is installed for this profile"
    rec=Inspection(organization_id=user.organization_id,profile_id=p.id,result=result,score=None,explanation=why); db.add(rec); audit(db,user,"inspection.run","inspection",rec.id,why); db.commit(); db.refresh(rec)
    return {"id":rec.id,"result":result,"score":None,"score_type":"not_available","profile_id":p.id,"profile_version":p.config_version,"model_version":None,"created_at":rec.created_at,"explanation":why}
@app.get("/api/v1/reviews")
def reviews(db:Session=Depends(get_db),user:User=Depends(current_user)):
    return db.scalars(select(Inspection).where(Inspection.organization_id==user.organization_id,Inspection.result.in_(["needs_review","unknown"])).order_by(Inspection.id.desc())).all()
@app.patch("/api/v1/reviews/{inspection_id}")
def review(inspection_id:int,data:ReviewUpdate,db:Session=Depends(get_db),user:User=Depends(require_roles("org_admin","quality_manager","engineer","operator"))):
    i=scoped(db,Inspection,inspection_id,user.organization_id); i.corrected_result=data.corrected_result; audit(db,user,"inspection.correct","inspection",i.id,data.note); db.commit(); return {"id":i.id,"original_result":i.result,"corrected_result":i.corrected_result,"note":data.note}
@app.get("/api/v1/audit")
def audit_log(limit:int=100,db:Session=Depends(get_db),user:User=Depends(require_roles("org_admin","quality_manager","read_only_auditor"))):
    return db.scalars(select(AuditEvent).where(AuditEvent.organization_id==user.organization_id).order_by(AuditEvent.id.desc()).limit(min(max(limit,1),500))).all()
@app.get("/api/v1/reports/inspections.csv")
def report(db:Session=Depends(get_db),user:User=Depends(current_user)):
    rows=db.scalars(select(Inspection).where(Inspection.organization_id==user.organization_id).order_by(Inspection.id)).all()
    import csv
    out=io.StringIO(); w=csv.writer(out); w.writerow(["id","profile_id","result","score","corrected_result","created_at"])
    for x in rows: w.writerow([x.id,x.profile_id,x.result,x.score,x.corrected_result,x.created_at])
    return StreamingResponse(iter([out.getvalue()]),media_type="text/csv",headers={"Content-Disposition":"attachment; filename=linecheck-inspections.csv"})
