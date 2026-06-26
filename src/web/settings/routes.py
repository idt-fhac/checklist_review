from __future__ import annotations

import re
import uuid
from typing import Any, Dict

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for

from src.core.types import LLMProvider
from src.web.settings.services import SettingsManager

settings_bp = Blueprint(
    "settings", __name__, url_prefix="/settings", template_folder="templates"
)


@settings_bp.route("/api/ollama/models", methods=["GET"])
def get_ollama_models_route():
    secrets = SettingsManager.load_secrets()
    ollama_providers = [p for p in secrets if p["type"] == "ollama"]

    base_url = (
        ollama_providers[0]["base_url"]
        if ollama_providers
        else "http://localhost:11434"
    )
    models = SettingsManager.get_ollama_models(base_url)
    return jsonify({"models": models})


@settings_bp.route("/api/ollama/check", methods=["GET"])
def check_ollama_route():
    url = request.args.get("url")
    if not url:
        return jsonify({"models": []})

    models = SettingsManager.get_ollama_models(url)
    return jsonify({"models": models})


@settings_bp.route("/api/openai/check", methods=["GET"])
def check_openai_route():
    base_url = request.args.get("base_url")
    api_key = request.args.get("api_key")
    port_str = request.args.get("port")

    if not base_url:
        return jsonify({"models": [], "error": "Base URL is required"})

    port = None
    if port_str:
        try:
            port = int(port_str)
        except ValueError:
            return jsonify({"models": [], "error": "Invalid port number"})

    try:
        models = SettingsManager.get_openai_models(base_url, api_key, port)
        return jsonify({"models": models})
    except Exception as e:
        return jsonify({"models": [], "error": str(e)})


@settings_bp.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        form_type = request.form.get("form_type")

        if form_type == "general_settings":
            _handle_general_settings(request.form)
            flash("General settings saved.", "success")

        elif form_type == "add_provider":
            try:
                _handle_add_provider(request.form)
                flash("Provider added successfully.", "success")
            except PermissionError as e:
                flash(str(e), "warning")
            except ValueError as e:
                flash(str(e), "danger")

        elif form_type == "delete_provider":
            provider_id = request.form.get("provider_id")
            try:
                _handle_delete_provider(provider_id)
                flash("Provider removed.", "success")
            except PermissionError as e:
                flash(str(e), "warning")

        elif form_type == "duplicate_provider":
            provider_id = request.form.get("provider_id")
            duplicate_name = request.form.get("duplicate_name")
            try:
                _handle_duplicate_provider(provider_id, duplicate_name)
                flash("Provider duplicated successfully.", "success")
            except ValueError as e:
                flash(str(e), "danger")

        elif form_type == "update_provider":
            try:
                _handle_update_provider(request.form)
                flash("Provider updated successfully.", "success")
            except ValueError as e:
                flash(str(e), "danger")

        return redirect(url_for("settings.index"))

    settings = SettingsManager.load_settings()
    secrets = SettingsManager.load_secrets()

    context = {
        "active_tab": "settings",
        "settings": settings,
        "providers": secrets,
    }
    return render_template("settings/index.html", **context)


@settings_bp.get("/api/settings")
def api_get_settings():
    settings = SettingsManager.load_settings()
    return jsonify(settings)


def _handle_general_settings(form: Dict[str, Any]):
    settings = SettingsManager.load_settings()

    # Visualization embedding settings
    embedding_type = form.get("embedding_model_type")
    if embedding_type:
        settings["embedding_model_type"] = embedding_type

    if embedding_type == "provider":
        embedding_provider_id = form.get("embedding_provider_id")
        if embedding_provider_id:
            settings["embedding_provider_id"] = embedding_provider_id
    else:
        ollama_model = form.get("embedding_ollama_model")
        if ollama_model is not None:
            settings["embedding_ollama_model"] = ollama_model

    default_page = form.get("default_page")
    if default_page:
        settings["default_page"] = default_page

    pdf_metadata_method = form.get("pdf_metadata_extraction_method")
    if pdf_metadata_method in {"llm", "rule_based"}:
        settings["pdf_metadata_extraction_method"] = pdf_metadata_method

    pdf_processing_provider_id = form.get("pdf_processing_llm_provider_id")
    if pdf_processing_provider_id is not None:
        if pdf_processing_provider_id == "":
            settings["pdf_processing_llm_provider_id"] = None
        else:
            settings["pdf_processing_llm_provider_id"] = pdf_processing_provider_id

    checklist_extraction_provider_id = form.get("checklist_extraction_llm_provider_id")
    if checklist_extraction_provider_id is not None:
        if checklist_extraction_provider_id == "":
            settings["checklist_extraction_llm_provider_id"] = None
        else:
            settings["checklist_extraction_llm_provider_id"] = (
                checklist_extraction_provider_id
            )

    SettingsManager.save_settings(settings)


def _handle_add_provider(form: Dict[str, Any]):
    provider_type = form.get("provider_type")
    name = form.get("name", "").strip()

    if not name:
        raise ValueError("Provider name is required.")

    is_embedding = form.get("is_embedding_model") == "on"
    new_provider: LLMProvider = {
        "id": str(uuid.uuid4()),
        "type": provider_type,
        "name": name,
        "base_url": "",
        "api_key": None,
        "model_name": None,
        "is_embedding_model": is_embedding,
        "accepts_image_input": form.get("accepts_image_input") == "on"
        and not is_embedding,
    }

    if provider_type == "ollama":
        base_url = form.get("ollama_base_url", "").strip()
        model_name = form.get("ollama_model_name", "").strip()

        if not base_url:
            raise ValueError("Ollama URL is required.")
        new_provider["base_url"] = base_url
        if model_name:
            new_provider["model_name"] = model_name

    elif provider_type == "openai":
        api_key = form.get("openai_api_key", "").strip()
        model_name = form.get("openai_model_name", "").strip()
        base_url = form.get("openai_base_url", "").strip()

        if not api_key:
            raise ValueError("API key is required for OpenAI provider.")
        if not model_name:
            raise ValueError("Model name is required for OpenAI provider.")

        new_provider["base_url"] = base_url
        new_provider["api_key"] = api_key
        new_provider["model_name"] = model_name

    elif provider_type == "gemini":
        api_key = form.get("gemini_api_key", "").strip()
        model_name = form.get("gemini_model_name", "").strip()

        if not api_key:
            raise ValueError("API key is required for Gemini provider.")
        if not model_name:
            raise ValueError("Model name is required for Gemini provider.")

        new_provider["base_url"] = ""  # Not used for Gemini
        new_provider["api_key"] = api_key
        new_provider["model_name"] = model_name

    elif provider_type == "litellm":
        base_url = form.get("litellm_base_url", "").strip()
        api_key = form.get("litellm_api_key", "").strip()
        model_name = form.get("litellm_model_name", "").strip()
        port_str = form.get("litellm_port", "").strip()

        if not base_url:
            raise ValueError("Base URL is required for LiteLLM provider.")
        if not model_name:
            raise ValueError("Model name is required for LiteLLM provider.")

        new_provider["base_url"] = base_url
        new_provider["api_key"] = api_key
        new_provider["model_name"] = model_name

        if port_str:
            try:
                new_provider["port"] = int(port_str)
            except ValueError:
                raise ValueError("Port must be a valid integer.")

    else:
        raise ValueError("Invalid provider type.")

    secrets = SettingsManager.load_secrets()
    secrets.append(new_provider)
    SettingsManager.save_secrets(secrets)


def _handle_delete_provider(provider_id: str):
    if not provider_id:
        return
    secrets = SettingsManager.load_secrets()
    secrets = [p for p in secrets if p["id"] != provider_id]
    SettingsManager.save_secrets(secrets)


def _build_default_duplicate_name(base_name: str, existing_names: set[str]) -> str:
    match = re.search(r" \(Copy(?: (\d+))?\)$", base_name)

    if match:
        base_name_without_copy = base_name[: match.start()]
        copy_num = match.group(1)
        next_num = int(copy_num) + 1 if copy_num else 2
        candidate = f"{base_name_without_copy} (Copy {next_num})"
    else:
        candidate = f"{base_name} (Copy)"

    original_candidate = candidate
    counter = 2
    while candidate in existing_names:
        candidate = f"{original_candidate} {counter}"
        counter += 1

    return candidate


def _handle_duplicate_provider(provider_id: str, duplicate_name: str | None = None):
    if not provider_id:
        raise ValueError("Provider ID is required.")

    secrets = SettingsManager.load_secrets()
    provider_to_duplicate = next((p for p in secrets if p["id"] == provider_id), None)

    if not provider_to_duplicate:
        raise ValueError("Provider not found.")

    import copy

    new_provider = copy.deepcopy(provider_to_duplicate)
    new_provider["id"] = str(uuid.uuid4())

    existing_names = {p["name"] for p in secrets}

    provided_name = (duplicate_name or "").strip()
    if provided_name:
        if provided_name in existing_names:
            raise ValueError("A provider with this name already exists.")
        new_name = provided_name
    else:
        new_name = _build_default_duplicate_name(new_provider["name"], existing_names)

    new_provider["name"] = new_name
    secrets.append(new_provider)
    SettingsManager.save_secrets(secrets)


def _handle_update_provider(form: Dict[str, Any]):
    provider_id = form.get("provider_id")
    if not provider_id:
        raise ValueError("Provider ID is required.")

    secrets = SettingsManager.load_secrets()
    provider = next((p for p in secrets if p["id"] == provider_id), None)

    if not provider:
        raise ValueError("Provider not found.")

    name = form.get("name", "").strip()
    if not name:
        raise ValueError("Provider name is required.")
    provider["name"] = name

    provider_type = form.get("provider_type")
    if not provider_type:
        raise ValueError("Provider type is required.")
    provider["type"] = provider_type

    if provider_type == "ollama":
        base_url = form.get("ollama_base_url", "").strip()
        model_name = form.get("ollama_model_name", "").strip()

        if not base_url:
            raise ValueError("Ollama URL is required.")
        provider["base_url"] = base_url
        provider["model_name"] = model_name if model_name else None
        provider["api_key"] = None

    elif provider_type == "openai":
        api_key = form.get("openai_api_key", "").strip()
        model_name = form.get("openai_model_name", "").strip()
        base_url = form.get("openai_base_url", "").strip()

        if not model_name:
            raise ValueError("Model name is required for OpenAI provider.")

        provider["base_url"] = base_url
        if api_key:
            provider["api_key"] = api_key
        provider["model_name"] = model_name
        provider.pop("port", None)  # Remove port if it exists
        provider.pop("params", None)  # Remove params if they exist

    elif provider_type == "gemini":
        api_key = form.get("gemini_api_key", "").strip()
        model_name = form.get("gemini_model_name", "").strip()

        if not model_name:
            raise ValueError("Model name is required for Gemini provider.")

        provider["base_url"] = ""  # Not used for Gemini
        if api_key:
            provider["api_key"] = api_key
        provider["model_name"] = model_name
        provider.pop("port", None)  # Remove port if it exists
        provider.pop("params", None)  # Remove params if they exist

    elif provider_type == "litellm":
        base_url = form.get("litellm_base_url", "").strip()
        api_key = form.get("litellm_api_key", "").strip()
        model_name = form.get("litellm_model_name", "").strip()
        port_str = form.get("litellm_port", "").strip()

        if not base_url:
            raise ValueError("Base URL is required for LiteLLM provider.")
        if not model_name:
            raise ValueError("Model name is required for LiteLLM provider.")

        provider["base_url"] = base_url
        if api_key:
            provider["api_key"] = api_key
        provider["model_name"] = model_name

        if port_str:
            try:
                provider["port"] = int(port_str)
            except ValueError:
                raise ValueError("Port must be a valid integer.")
        else:
            provider.pop("port", None)

    else:
        raise ValueError("Invalid provider type.")

    # Handle embedding and direct upload flags
    is_embedding = form.get("is_embedding_model") == "on"
    provider["is_embedding_model"] = is_embedding
    # Image input is only for non-embedding models
    if is_embedding:
        provider["accepts_image_input"] = False
    else:
        provider["accepts_image_input"] = form.get("accepts_image_input") == "on"

    SettingsManager.save_secrets(secrets)
