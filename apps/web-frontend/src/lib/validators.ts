import { z } from "zod";

import type { SigninRequest, SignupRequest } from "@/lib/api";

const usernamePattern = /^[a-zA-Z0-9_]+$/;

export const signinSchema = z.object({
  login: z.string().min(3, "Enter your email or username"),
  password: z.string().min(1, "Password is required"),
});

export type SigninValues = SigninRequest;

export const signupSchema = z.object({
  first_name: z.string().trim().min(1, "First name is required").max(50),
  last_name: z.string().trim().min(1, "Last name is required").max(50),
  username: z
    .string()
    .trim()
    .min(3, "Username must be at least 3 characters")
    .max(30, "Username must be at most 30 characters")
    .regex(
      usernamePattern,
      "Username must contain only letters, numbers, and underscores"
    ),
  email: z.string().email("Enter a valid email address"),
  password: z
    .string()
    .min(8, "Password must be at least 8 characters")
    .regex(/[A-Z]/, "Password must contain at least one uppercase letter")
    .regex(/[a-z]/, "Password must contain at least one lowercase letter")
    .regex(/\d/, "Password must contain at least one digit"),
});

export type SignupValues = SignupRequest;
