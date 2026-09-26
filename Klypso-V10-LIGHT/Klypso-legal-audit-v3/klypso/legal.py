from flask import Blueprint, current_app, render_template, Response

legal_bp = Blueprint("legal", __name__)


def display(value, fallback="[À COMPLÉTER]"):
    return value if value else fallback


def legal_context():
    c = current_app.config
    return {
        "entity_name": display(c["LEGAL_ENTITY_NAME"]),
        "legal_status": display(c["LEGAL_STATUS"]),
        "legal_address": display(c["LEGAL_ADDRESS"]),
        "legal_siret": display(c["LEGAL_SIRET"]),
        "legal_rcs": display(c["LEGAL_RCS"], "[À COMPLÉTER SI APPLICABLE]"),
        "legal_vat": display(c["LEGAL_VAT"], "[À COMPLÉTER SI APPLICABLE]"),
        "publication_director": display(c["LEGAL_PUBLICATION_DIRECTOR"]),
        "contact_email": display(c["LEGAL_CONTACT_EMAIL"]),
        "contact_phone": display(c["LEGAL_CONTACT_PHONE"], "[À COMPLÉTER SI VOUS LE PUBLIEZ]"),
        "privacy_email": display(c["PRIVACY_CONTACT_EMAIL"] or c["LEGAL_CONTACT_EMAIL"]),
        "hoster_name": display(c["HOSTER_NAME"]),
        "hoster_address": display(c["HOSTER_ADDRESS"]),
        "hoster_phone": display(c["HOSTER_PHONE"]),
        "mediator_name": display(c["MEDIATOR_NAME"], "[MÉDIATEUR À CHOISIR ET À RENSEIGNER]"),
        "mediator_address": display(c["MEDIATOR_ADDRESS"]),
        "mediator_website": display(c["MEDIATOR_WEBSITE"]),
        "stripe_enabled": bool(c["STRIPE_SECRET_KEY"] and c["STRIPE_PRO_PRICE_ID"] and c["STRIPE_ULTRA_PRICE_ID"]),
        "prices_are_ttc": c["PRICES_ARE_TTC"],
        "public_base_url": c["PUBLIC_BASE_URL"],
        "cgu_version": c["CGU_VERSION"],
        "privacy_version": c["PRIVACY_VERSION"],
        "cookie_policy_version": c["COOKIE_POLICY_VERSION"],
        "accessibility_declaration_enabled": c["ACCESSIBILITY_DECLARATION_ENABLED"],
    }


@legal_bp.app_context_processor
def inject_legal_context():
    return {"legal": legal_context()}


@legal_bp.get("/mentions-legales")
def mentions_legales():
    return render_template("legal/mentions-legales.html")


@legal_bp.get("/politique-confidentialite")
def confidentialite():
    return render_template("legal/confidentialite.html")


@legal_bp.get("/cookies")
def cookies():
    return render_template("legal/cookies.html")


@legal_bp.get("/cgu")
def cgu():
    return render_template("legal/cgu.html")


@legal_bp.get("/cgv")
def cgv():
    return render_template("legal/cgv.html")


@legal_bp.get("/contact")
def contact():
    return render_template("legal/contact.html")


@legal_bp.get("/suppression-compte")
def suppression_compte():
    return render_template("legal/suppression-compte.html")


@legal_bp.get("/retractation")
def retractation():
    return render_template("legal/retractation.html")


@legal_bp.get("/accessibilite")
def accessibilite():
    return render_template("legal/accessibilite.html")


@legal_bp.get("/robots.txt")
def robots():
    base = current_app.config["PUBLIC_BASE_URL"]
    body = f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n"
    return Response(body, mimetype="text/plain")


@legal_bp.get("/sitemap.xml")
def sitemap():
    base = current_app.config["PUBLIC_BASE_URL"]
    routes = [
        "/",
        "/pricing",
        "/mentions-legales",
        "/politique-confidentialite",
        "/cookies",
        "/cgu",
        "/cgv",
        "/contact",
        "/retractation",
        "/accessibilite",
    ]
    urls = "".join(f"<url><loc>{base}{path}</loc></url>" for path in routes)
    xml = f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>'
    return Response(xml, mimetype="application/xml")


@legal_bp.get("/llms.txt")
def llms():
    base = current_app.config["PUBLIC_BASE_URL"]
    body = f"""# KLYPSO\n\nKlypso est une plateforme web de création vidéo destinée aux créateurs, notamment streamers et YouTubeurs. Elle propose Klypso Clips pour l'analyse et la création de formats courts, ainsi que Klypso Studio pour le montage vidéo.\n\n## Pages publiques\n- Accueil: {base}/\n- Tarifs: {base}/pricing\n- Mentions légales: {base}/mentions-legales\n- Confidentialité: {base}/politique-confidentialite\n- Cookies: {base}/cookies\n- CGU: {base}/cgu\n- CGV: {base}/cgv\n- Contact: {base}/contact\n- Rétractation: {base}/retractation\n- Accessibilité: {base}/accessibilite\n\nLe contenu contractuel et les informations d'identification doivent être vérifiés avant mise en production.\n"""
    return Response(body, mimetype="text/plain")
