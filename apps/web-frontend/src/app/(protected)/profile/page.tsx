"use client";

import Link from "next/link";
import { ArrowLeft, Mail, Upload, User as UserIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { useAuth } from "@/lib/auth-context";

export default function ProfilePage() {
  const { user } = useAuth();

  if (!user) return null;

  const initials = `${user.first_name[0]}${user.last_name[0]}`;

  return (
    <div className="mx-auto max-w-2xl px-6 py-8">
      <Link
        href="/dashboard"
        className="mb-4 inline-flex items-center text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="mr-1 size-3.5" />
        Back to dashboard
      </Link>

      <h1 className="text-2xl font-bold tracking-tight">Profile</h1>
      <p className="text-sm text-muted-foreground">
        Manage your account details.
      </p>

      <Separator className="my-6" />

      {/* User info card */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-4">
            <div className="flex size-16 items-center justify-center rounded-full bg-primary text-xl font-bold text-primary-foreground">
              {initials}
            </div>
            <div>
              <CardTitle>
                {user.first_name} {user.last_name}
              </CardTitle>
              <CardDescription>@{user.username}</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center gap-3 rounded-md border px-4 py-3">
            <Mail className="size-4 text-muted-foreground" />
            <div>
              <p className="text-xs text-muted-foreground">Email</p>
              <p className="text-sm">{user.email}</p>
            </div>
          </div>

          <div className="flex items-center gap-3 rounded-md border px-4 py-3">
            <UserIcon className="size-4 text-muted-foreground" />
            <div>
              <p className="text-xs text-muted-foreground">Username</p>
              <p className="text-sm">{user.username}</p>
            </div>
          </div>

          <div className="flex items-center gap-3 rounded-md border px-4 py-3">
            <div className="size-4" />
            <div>
              <p className="text-xs text-muted-foreground">Member since</p>
              <p className="text-sm">
                {new Date(user.created_at).toLocaleDateString("en-US", {
                  month: "long",
                  day: "numeric",
                  year: "numeric",
                })}
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      <Separator className="my-6" />

      {/* Resume section */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Upload className="size-4" />
            Resume
          </CardTitle>
          <CardDescription>
            Upload your resume to enable AI-powered ticket assignment. Your
            skills and experience will be used to match you with relevant
            tickets.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between rounded-md border border-dashed px-4 py-3">
            <div className="flex items-center gap-2">
              <Badge variant="outline" className="text-xs">
                No resume uploaded
              </Badge>
            </div>
            <Link href="/profile/resume">
              <Button size="sm">
                <Upload className="mr-1.5 size-3.5" />
                Upload resume
              </Button>
            </Link>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}