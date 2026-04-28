from flask import Blueprint, request, redirect, url_for, flash, render_template, session
from src.core.workspace import (
    list_workspaces,
    get_active_workspace,
    set_active_workspace,
    create_workspace,
    delete_workspace,
    duplicate_workspace,
    is_reserved_workspace_name,
)

workspace_bp = Blueprint("workspace", __name__, url_prefix="/workspace", template_folder="templates")

@workspace_bp.route("/manage", methods=["GET"])
def manage():
    workspaces = list_workspaces()
    active_workspace = get_active_workspace()
    show_workspace_onboarding = session.pop("show_new_workspace_onboarding", False)
    return render_template(
        "workspace/manage.html",
        workspaces=workspaces,
        active_workspace=active_workspace,
        show_workspace_onboarding=show_workspace_onboarding,
    )

@workspace_bp.route("/switch", methods=["POST"])
def switch_workspace():
    workspace_name = request.form.get("workspace_name")
    if workspace_name and workspace_name in list_workspaces():
        set_active_workspace(workspace_name)
        flash(f"Switched to workspace '{workspace_name}'", "success")
    else:
        flash("Invalid workspace selected.", "danger")
    return redirect(request.referrer or url_for("checklist_review.index"))

@workspace_bp.route("/create", methods=["POST"])
def create_new_workspace():
    workspace_name = request.form.get("workspace_name", "").strip()
    if not workspace_name:
        flash("Workspace name cannot be empty.", "danger")
    elif is_reserved_workspace_name(workspace_name):
        flash(
            f"The name '{workspace_name}' is reserved. Choose a different workspace name.",
            "danger",
        )
    elif create_workspace(workspace_name):
        set_active_workspace(workspace_name)
        session["show_new_workspace_onboarding"] = True
        flash(f"Workspace '{workspace_name}' created and activated.", "success")
        return redirect(url_for("workspace.manage"))
    else:
        flash(f"Workspace '{workspace_name}' already exists or is invalid.", "danger")
    return redirect(request.referrer or url_for("checklist_review.index"))


@workspace_bp.route("/duplicate", methods=["POST"])
def post_duplicate_workspace():
    source_name = (request.form.get("source_workspace_name") or "").strip()
    new_name = (request.form.get("new_workspace_name") or "").strip()
    if not source_name or not new_name:
        flash("Source workspace and new name are required.", "danger")
    elif is_reserved_workspace_name(new_name):
        flash(
            f"The name '{new_name}' is reserved. Choose a different workspace name.",
            "danger",
        )
    elif new_name == source_name:
        flash("The new workspace name must differ from the source.", "danger")
    elif duplicate_workspace(source_name, new_name):
        set_active_workspace(new_name)
        flash(
            f"Workspace '{new_name}' created with settings and secrets copied from '{source_name}'.",
            "success",
        )
    else:
        flash(
            "Could not duplicate the workspace. The name may already exist, or the source is invalid.",
            "danger",
        )
    return redirect(url_for("workspace.manage"))

@workspace_bp.route("/delete", methods=["POST"])
def delete_existing_workspace():
    workspace_name = request.form.get("workspace_name")
    if workspace_name == "guest":
        flash("Cannot delete the guest workspace.", "danger")
    elif delete_workspace(workspace_name):
        flash(f"Workspace '{workspace_name}' deleted successfully.", "success")
    else:
        flash(f"Failed to delete workspace '{workspace_name}'.", "danger")
    return redirect(url_for("workspace.manage"))
