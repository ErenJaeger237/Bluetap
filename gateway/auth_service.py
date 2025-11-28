import uuid
import random
from generated import bluetap_pb2 as pb
from generated import bluetap_pb2_grpc as rpc
from .db import MetadataDB

db = MetadataDB()

class AuthService(rpc.AuthServiceServicer):

    def Login(self, req, ctx):
        print(f"[Auth] Login request for {req.username}")

        # Check password
        if not db.verify_password(req.username, req.password):
            return pb.LoginResponse(
                next_action="error",
                message="Invalid username or password"
            )

        # Generate OTP
        otp = str(random.randint(100000, 999999))
        db.save_otp(req.username, otp)

        print(f"[Auth] OTP for {req.username}: {otp}")  # visible for debugging

        return pb.LoginResponse(
            next_action="otp_required",
            message="OTP sent to registered email"
        )

    def RequestOTP(self, req, ctx):
        otp = str(random.randint(100000, 999999))
        db.save_otp(req.username, otp)
        print(f"[Auth] OTP for {req.username}: {otp}")
        return pb.RequestOTPResponse(ok=True, message="OTP sent")

    def VerifyOTP(self, req, ctx):
        ok, msg = db.verify_otp(req.username, req.otp_code)
        if not ok:
            return pb.VerifyOTPResponse(ok=False, message=msg)

        # Issue token
        token = str(uuid.uuid4())
        db.save_token(req.username, token)

        return pb.VerifyOTPResponse(
            ok=True,
            message="OTP verified",
            token=token
        )

    def ValidateToken(self, req, ctx):
        valid, username = db.validate_token(req.token)
        return pb.ValidateTokenResponse(valid=valid, username=username or "")
