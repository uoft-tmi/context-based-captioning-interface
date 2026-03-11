from fastapi import APIRouter, Depends, HTTPException, Request

router = APIRouter(prefix="/model", tags=["model"])
