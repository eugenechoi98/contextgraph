import express from "express";
import { loginHandler, verifyToken } from "./auth";

const router = express.Router();

router.post("/login", loginHandler);
router.get("/verify", verifyToken);

export default router;
