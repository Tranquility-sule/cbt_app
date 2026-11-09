from flask import Blueprint, request, jsonify

from faq_data import match_faq

support_bp = Blueprint("support", __name__)


@support_bp.route("/support/ask", methods=["POST"])
def ask():
    data = request.get_json(force=True, silent=True) or {}
    message = data.get("message", "")
    if not message.strip():
        return jsonify({"answer": "Type a question and I'll try to help."})

    answer = match_faq(message)
    return jsonify({"answer": answer})
