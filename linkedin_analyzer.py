"""
linkedin_analyzer.py — LinkedIn Profile Analyzer
Scores a pasted LinkedIn profile across key criteria.
"""
import re


LINKEDIN_SECTIONS = {
    "Headline":     r'(headline|software|engineer|developer|manager|analyst|scientist|designer|consultant)',
    "About":        r'(about|summary|i am|i\'m|my experience|passionate|dedicated)',
    "Experience":   r'(experience|worked at|working at|company|position|role|engineer|manager)',
    "Education":    r'(education|university|college|degree|bachelor|master|phd|graduated)',
    "Skills":       r'(skills|python|java|sql|machine learning|react|aws|management|analytics)',
    "Certifications": r'(certif|aws certified|google|microsoft|coursera|udemy|license)',
    "Recommendations": r'(recommend|endorsed|colleague|worked with)',
    "Accomplishments": r'(award|publication|patent|honor|project|volunteer)',
}

ACTION_WORDS = [
    "led","managed","developed","built","created","designed","implemented",
    "launched","delivered","drove","achieved","improved","increased","reduced",
    "spearheaded","architected","collaborated","mentored","trained","optimized",
    "generated","scaled","streamlined","executed","established","coordinated",
]

WEAK_WORDS = [
    "responsible for","duties","tasks","helped","assisted","participated",
    "worked on","tried","attempted","involved in",
]

POWER_KEYWORDS = [
    "python","machine learning","data science","sql","aws","azure","react",
    "javascript","leadership","agile","scrum","project management","analytics",
    "product management","strategy","innovation","stakeholder","cross-functional",
    "revenue","growth","kpi","roi","b2b","saas","api","cloud","devops",
]


class LinkedInAnalyzer:

    def analyze(self, profile_text: str) -> dict:
        lower = profile_text.lower()
        word_count = len(profile_text.split())

        # 1. Profile completeness (25 pts)
        comp_score, comp_detail = self._score_completeness(lower)

        # 2. Headline strength (15 pts)
        hl_score, hl_detail = self._score_headline(profile_text, lower)

        # 3. About / Summary quality (20 pts)
        about_score, about_detail = self._score_about(lower, word_count)

        # 4. Keywords (20 pts)
        kw_score, kw_found, kw_missing = self._score_keywords(lower)

        # 5. Writing quality (10 pts)
        wq_score, wq_detail = self._score_writing(lower)

        # 6. Experience depth (10 pts)
        exp_score, exp_detail = self._score_experience(lower)

        weights = {
            "Profile Completeness": 25,
            "Headline Strength":    15,
            "About / Summary":      20,
            "Keywords":             20,
            "Writing Quality":      10,
            "Experience Depth":     10,
        }
        raw = {
            "Profile Completeness": comp_score,
            "Headline Strength":    hl_score,
            "About / Summary":      about_score,
            "Keywords":             kw_score,
            "Writing Quality":      wq_score,
            "Experience Depth":     exp_score,
        }

        total = sum((raw[k] / 100) * weights[k] for k in weights)
        overall = round(min(99, max(10, total)))

        breakdown = {k: round((raw[k]/100)*weights[k], 1) for k in weights}

        improvements = self._build_improvements(raw, comp_detail, hl_detail,
                                                 about_detail, kw_missing, wq_detail)

        return {
            "overall_score":    overall,
            "score_breakdown":  breakdown,
            "max_breakdown":    weights,
            "found_keywords":   kw_found[:20],
            "missing_keywords": kw_missing[:12],
            "improvements":     improvements,
            "word_count":       word_count,
        }

    def _score_completeness(self, lower):
        found, missing = [], []
        for section, pattern in LINKEDIN_SECTIONS.items():
            if re.search(pattern, lower):
                found.append(section)
            else:
                missing.append(section)
        score = round((len(found) / len(LINKEDIN_SECTIONS)) * 100)
        return score, {"found": found, "missing": missing}

    def _score_headline(self, text, lower):
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        headline = lines[0] if lines else ''
        score = 40
        detail = {"headline": headline}
        if len(headline) > 20:  score += 20
        if len(headline) > 50:  score += 15
        if '|' in headline or '·' in headline: score += 15  # formatted
        if re.search(r'(engineer|manager|scientist|analyst|developer|designer|director|lead)', lower): score += 10
        return min(100, score), detail

    def _score_about(self, lower, word_count):
        score = 20
        detail = {}
        if re.search(r'(about|summary|i am|passionate|experienced)', lower): score += 20
        if word_count > 100: score += 20
        if word_count > 200: score += 20
        if word_count > 300: score += 10
        if re.search(r'\d+\s*(year|month)', lower): score += 10  # mentions years of exp
        return min(100, score), detail

    def _score_keywords(self, lower):
        found = [k for k in POWER_KEYWORDS if k in lower]
        missing = [k for k in POWER_KEYWORDS if k not in lower]
        n = len(found)
        if n == 0:      score = 10
        elif n <= 3:    score = 30 + n * 10
        elif n <= 7:    score = 60 + (n-3) * 7
        elif n <= 12:   score = 88 + (n-7) * 2
        else:           score = 98
        return round(min(98, score)), found, missing[:12]

    def _score_writing(self, lower):
        verbs = [v for v in ACTION_WORDS if v in lower]
        weak  = [w for w in WEAK_WORDS if w in lower]
        score = min(98, 30 + len(verbs)*8 - len(weak)*10)
        return max(20, score), {"verbs": verbs, "weak": weak}

    def _score_experience(self, lower):
        score = 30
        if re.search(r'(experience|worked|company|position)', lower): score += 20
        job_count = len(re.findall(r'\b(20\d\d|19\d\d)\b', lower))
        score += min(30, job_count * 8)
        if re.search(r'\d+\s*%|\$[\d,]+|\d+[mk]\b', lower): score += 20
        return min(100, score), {}

    def _build_improvements(self, raw, comp, hl, about, kw_missing, wq):
        tips = []

        if raw["Profile Completeness"] < 80:
            missing = comp.get("missing", [])
            tips.append({
                "priority": "HIGH",
                "category": "Profile Completeness",
                "issue": f"Missing sections: {', '.join(missing[:4])}",
                "fix": "Complete every section of your LinkedIn profile. Profiles with all sections filled get 40x more views than incomplete ones."
            })

        if raw["Headline Strength"] < 70:
            tips.append({
                "priority": "HIGH",
                "category": "Headline",
                "issue": "Headline needs to be stronger and more descriptive",
                "fix": "Write a headline like: 'Senior Data Scientist | Machine Learning | Python | AWS | Helping companies make data-driven decisions'. Use keywords recruiters search for."
            })

        if raw["About / Summary"] < 60:
            tips.append({
                "priority": "HIGH",
                "category": "About Section",
                "issue": "About section is too short or missing",
                "fix": "Write 3-5 paragraphs (300+ words) in your About section. Include your background, key skills, achievements with numbers, and what you're looking for."
            })

        if raw["Keywords"] < 60:
            tips.append({
                "priority": "MEDIUM",
                "category": "Keywords",
                "issue": "Low keyword density — harder for recruiters to find you",
                "fix": f"Add these keywords naturally to your profile: {', '.join(kw_missing[:6])}. LinkedIn's algorithm ranks profiles by keyword relevance."
            })

        if raw["Writing Quality"] < 60:
            tips.append({
                "priority": "MEDIUM",
                "category": "Writing Quality",
                "issue": "Experience bullets lack action verbs and impact",
                "fix": "Start every experience bullet with a strong action verb. Add numbers: 'Led a team of 8', 'Increased revenue by 32%', 'Reduced costs by $200K'."
            })

        tips.sort(key=lambda x: {"HIGH":0,"MEDIUM":1,"LOW":2}.get(x["priority"],3))
        return tips
