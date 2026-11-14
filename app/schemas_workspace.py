from datetime import datetime

from pydantic import BaseModel, Field


class WorkspaceOut(BaseModel):
    id: int
    name: str
    slug: str
    workspace_type: str
    owner_user_id: int
    settings: dict = {}
    created_at: datetime

    class Config:
        from_attributes = True


class WorkspaceCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    workspace_type: str = Field(default="creator", pattern="^(creator|agency)$")


class WorkspaceSettingsIn(BaseModel):
    settings: dict = Field(default_factory=dict)


class MemberOut(BaseModel):
    id: int
    user_id: int
    email: str = ""
    name: str = ""
    role: str
    status: str
    joined_at: datetime | None = None

    class Config:
        from_attributes = True


class InviteIn(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    role: str = Field(default="editor", pattern="^(admin|manager|editor|finance|viewer)$")


class InviteOut(BaseModel):
    id: int
    email: str
    role: str
    expires_at: datetime
    accept_token: str = ""

    class Config:
        from_attributes = True


class AcceptInviteIn(BaseModel):
    token: str = Field(min_length=8, max_length=80)


class MemberRoleIn(BaseModel):
    role: str = Field(pattern="^(admin|manager|editor|finance|viewer)$")


class DealAssignmentIn(BaseModel):
    user_id: int
    assignment_role: str = Field(default="contributor", pattern="^(lead|contributor|reviewer)$")


class DealAssignmentOut(BaseModel):
    id: int
    deal_id: int
    user_id: int
    assignment_role: str

    class Config:
        from_attributes = True


class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = ""
    deal_id: int | None = None
    assignee_user_id: int | None = None
    due_at: datetime | None = None


class TaskPatchIn(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    status: str | None = Field(None, pattern="^(open|in_progress|done|cancelled)$")
    assignee_user_id: int | None = None
    due_at: datetime | None = None


class TaskOut(BaseModel):
    id: int
    workspace_id: int
    deal_id: int | None
    title: str
    description: str
    status: str
    assignee_user_id: int | None
    created_by_user_id: int
    due_at: datetime | None
    created_at: datetime

    class Config:
        from_attributes = True


class ActivityOut(BaseModel):
    id: int
    action: str
    detail: str
    user_id: int | None
    resource_type: str
    resource_id: int | None
    created_at: datetime

    class Config:
        from_attributes = True


class TransferOwnerIn(BaseModel):
    new_owner_user_id: int
    confirm: bool = False


class DeleteWorkspaceIn(BaseModel):
    confirm_name: str
    confirm: bool = False
