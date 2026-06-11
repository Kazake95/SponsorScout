def score_job(job, profile):
    score = 0
    text = f"{job.title} {job.description}".lower()
    for skill in profile.get("skills", []):
        if skill.lower() in text:
            score += 8
    for title in profile.get("titles", []):
        if title.lower() in job.title.lower():
            score += 20
    if job.country in profile.get("countries", []):
        score += 15
    if getattr(job, "sponsorship_score", 0) >= 70:
        score += 15
    if "remote" in (job.location or "").lower():
        score += 5
    if "english" in (job.description or "").lower():
        score += 2
    return min(score, 100)
