def format_profile_text(p: dict) -> str:
    name = p.get("full_name") or ""
    age = p.get("age") or ""
    city = p.get("city") or ""
    bio = p.get("bio") or ""

    lines = [
        f"👤 {name}, {age}",
        f"🏙️ {city}",
    ]
    if bio:
        lines.append("")
        lines.append(f"📝 {bio}")
    return "\n".join(lines)
