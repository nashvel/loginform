import smtplib
import random
from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy import Column, String, Integer
from pydantic import BaseModel, EmailStr
from db_config import Base, engine, get_db
import bcrypt
from fastapi.middleware.cors import CORSMiddleware


app = FastAPI()

# Allow CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Allow frontend origin
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods (POST, GET, etc.)
    allow_headers=["*"],  # Allow all headers
)


# Database Table
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(255), unique=True, nullable=False)
    password = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    is_verified = Column(Integer, default=0)  # 0 = Not Verified, 1 = Verified

class VerificationCode(Base):
    __tablename__ = "verification_codes"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False)
    code = Column(String(6), nullable=False)

# Ensure tables are created
Base.metadata.create_all(bind=engine)

# Request Schemas
class UserSignUp(BaseModel):
    username: str
    email: EmailStr
    password: str

class UserSignIn(BaseModel):
    username: str
    password: str

class UserVerification(BaseModel):
    email: EmailStr
    code: str

# Helper function to send email
def send_verification_email(to_email: str, code: str):
    smtp_server = "smtp.gmail.com"
    smtp_port = 587
    sender_email = "nacht.system@gmail.com"
    sender_password = "nngl cwvj bapf zixr" 

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            message = f"Subject: Verify Your Email\n\nYour verification code is: {code}"
            server.sendmail(sender_email, to_email, message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send email: {str(e)}")

# Signup Route
@app.post("/api/signup")
def signup(user: UserSignUp, db: Session = Depends(get_db)):
    # Check if user already exists
    existing_user = db.query(User).filter(User.email == user.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    # ✅ Hash the password at signup
    hashed_password = bcrypt.hashpw(user.password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    # ✅ Create user but set `is_verified = 0`
    new_user = User(username=user.username, email=user.email, password=hashed_password, is_verified=0)
    db.add(new_user)
    db.commit()

    # Generate verification code
    verification_code = str(random.randint(100000, 999999))

    # Send verification email
    send_verification_email(user.email, verification_code)

    # Save verification code to DB
    existing_code = db.query(VerificationCode).filter(VerificationCode.email == user.email).first()
    if existing_code:
        db.delete(existing_code)
        db.commit()

    new_code = VerificationCode(email=user.email, code=verification_code)
    db.add(new_code)
    db.commit()

    return {"message": "Verification code sent to email. Please verify your email first."}



# Verify Email Route
@app.post("/api/verify")
def verify_email(data: UserVerification, db: Session = Depends(get_db)):
    # Check if code exists for the email
    code_entry = db.query(VerificationCode).filter(VerificationCode.email == data.email).first()
    if not code_entry or code_entry.code != data.code:
        raise HTTPException(status_code=400, detail="Invalid or expired verification code")

    # Find the user in the database
    existing_user = db.query(User).filter(User.email == data.email).first()
    if not existing_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Mark the user as verified
    existing_user.is_verified = 1
    db.commit()

    # Delete verification code after successful verification
    db.delete(code_entry)
    db.commit()

    return {"message": "Email verified successfully. You can now log in."}




# Signin Route
@app.post("/api/login")
def login(user: UserSignIn, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.username == user.username).first()
    if not existing_user:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    print(f"User entered password: {user.password}")  # Debugging
    print(f"Stored hashed password: {existing_user.password}")  # Debugging

    # Verify password
    password_matches = bcrypt.checkpw(user.password.encode("utf-8"), existing_user.password.encode("utf-8"))
    print(f"Password match: {password_matches}")  # Debugging

    if not password_matches:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    if existing_user.is_verified == 0:
        raise HTTPException(status_code=403, detail="Email not verified")

    return {"username": existing_user.username}

class PasswordResetRequest(BaseModel):
    username: str  # Change from email to username

@app.post("/api/send-reset-code")
def send_reset_code(request: PasswordResetRequest, db: Session = Depends(get_db)):
    # ✅ Find user by username instead of email
    user = db.query(User).filter(User.username == request.username).first()
    if not user:
        raise HTTPException(status_code=404, detail="Username not found")

    # ✅ Use the retrieved email
    reset_code = str(random.randint(100000, 999999))

    # ✅ Send email to the associated email
    send_verification_email(user.email, reset_code)

    # ✅ Save reset code
    existing_code = db.query(VerificationCode).filter(VerificationCode.email == user.email).first()
    if existing_code:
        db.delete(existing_code)
        db.commit()

    new_code = VerificationCode(email=user.email, code=reset_code)
    db.add(new_code)
    db.commit()

    return {
    "message": f"Password reset code sent to {user.email}.",
    "email": user.email  # ✅ Add this line
    }



class PasswordResetVerify(BaseModel):
    email: EmailStr
    code: str
    new_password: str  # ✅ Ensure new_password is here

@app.post("/api/reset-password")
def reset_password(data: PasswordResetVerify, db: Session = Depends(get_db)):
    print("Received data:", data)  # ✅ Debugging
    if not data.email or not data.code or not data.new_password:
        raise HTTPException(status_code=400, detail="Missing required fields")

    code_entry = db.query(VerificationCode).filter(
        VerificationCode.email == data.email, VerificationCode.code == data.code
    ).first()

    if not code_entry:
        raise HTTPException(status_code=400, detail="Invalid or expired verification code")

    user = db.query(User).filter(User.email == data.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    hashed_password = bcrypt.hashpw(data.new_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    user.password = hashed_password
    db.commit()

    db.delete(code_entry)
    db.commit()

    return {"message": "Password reset successful! You can now log in."}
