from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from .auth import login_required
from .database import get_db
from .plans import get_plan, trial_ends_at
from .promo import effective_plan_key

billing_bp = Blueprint("billing", __name__)


@billing_bp.get("/pricing")
def pricing():
    return render_template("pricing.html")


@billing_bp.get("/payments")
@login_required
def payments():
    with get_db(current_app.config["DATABASE_PATH"]) as db:
        user = db.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
    key = effective_plan_key(user)
    return render_template("payments.html", user=user, plan=get_plan(key), effective_plan_key=key)


@billing_bp.get("/subscription")
@login_required
def subscription():
    with get_db(current_app.config["DATABASE_PATH"]) as db:
        user = db.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
    plan_key = effective_plan_key(user)
    trial_end = trial_ends_at(user["trial_started_at"])
    return render_template("subscription.html", user=user, plan=get_plan(plan_key), effective_plan_key=plan_key, trial_end=trial_end)


@billing_bp.post("/billing/checkout")
@login_required
def checkout():
    plan_key = request.form.get("plan")
    billing_interval = request.form.get("billing_interval", "monthly")
    if billing_interval not in {"monthly", "annual"}:
        billing_interval = "monthly"
    if request.form.get("accept_cgv") != "on":
        flash("Tu dois accepter les CGV avant de poursuivre le paiement.", "error")
        return redirect(url_for("billing.pricing"))

    price_id = {
        ("pro", "monthly"): current_app.config["STRIPE_PRO_PRICE_ID"],
        ("ultra", "monthly"): current_app.config["STRIPE_ULTRA_PRICE_ID"],
        ("pro", "annual"): current_app.config["STRIPE_PRO_ANNUAL_PRICE_ID"],
        ("ultra", "annual"): current_app.config["STRIPE_ULTRA_ANNUAL_PRICE_ID"],
    }.get((plan_key, billing_interval))
    if not current_app.config["STRIPE_SECRET_KEY"] or not price_id:
        flash("Stripe n'est pas encore configuré avec les identifiants réels.", "error")
        return redirect(url_for("billing.pricing"))

    try:
        import stripe
        stripe.api_key = current_app.config["STRIPE_SECRET_KEY"]
        with get_db(current_app.config["DATABASE_PATH"]) as db:
            user = db.execute("SELECT email,stripe_customer_id FROM users WHERE id=?", (session["user_id"],)).fetchone()

        kwargs = dict(
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=current_app.config["STRIPE_SUCCESS_URL"],
            cancel_url=current_app.config["STRIPE_CANCEL_URL"],
            metadata={"user_id": str(session["user_id"]), "plan": plan_key, "billing_interval": billing_interval},
            subscription_data={"metadata": {"user_id": str(session["user_id"]), "plan": plan_key, "billing_interval": billing_interval}, "trial_period_days": current_app.config["STRIPE_TRIAL_DAYS"]},
            payment_method_collection="always",
            client_reference_id=str(session["user_id"]),
            customer_email=user["email"] if not user["stripe_customer_id"] else None,
        )
        if user["stripe_customer_id"]:
            kwargs.pop("customer_email", None)
            kwargs["customer"] = user["stripe_customer_id"]
        checkout_session = stripe.checkout.Session.create(**kwargs)
        return redirect(checkout_session.url, code=303)
    except Exception as exc:
        current_app.logger.exception("Stripe checkout failed: %s", type(exc).__name__)
        flash("Le paiement n'a pas pu être démarré.", "error")
        return redirect(url_for("billing.pricing"))


@billing_bp.post("/billing/portal")
@login_required
def portal():
    if not current_app.config["STRIPE_SECRET_KEY"]:
        flash("Le portail Stripe n'est pas configuré.", "error")
        return redirect(url_for("billing.subscription"))
    with get_db(current_app.config["DATABASE_PATH"]) as db:
        user = db.execute("SELECT stripe_customer_id FROM users WHERE id=?", (session["user_id"],)).fetchone()
    if not user or not user["stripe_customer_id"]:
        flash("Aucun abonnement Stripe actif n'est associé à ce compte.", "error")
        return redirect(url_for("billing.subscription"))
    try:
        import stripe
        stripe.api_key = current_app.config["STRIPE_SECRET_KEY"]
        portal_session = stripe.billing_portal.Session.create(
            customer=user["stripe_customer_id"],
            return_url=current_app.config["STRIPE_PORTAL_RETURN_URL"],
        )
        return redirect(portal_session.url, code=303)
    except Exception as exc:
        current_app.logger.exception("Stripe portal failed: %s", type(exc).__name__)
        flash("Impossible d'ouvrir la gestion de l'abonnement.", "error")
        return redirect(url_for("billing.subscription"))


@billing_bp.post("/billing/webhook")
def webhook():
    secret = current_app.config["STRIPE_WEBHOOK_SECRET"]
    if not secret:
        return {"error": "Stripe webhook non configuré"}, 503
    import stripe
    payload = request.get_data()
    signature = request.headers.get("Stripe-Signature", "")
    try:
        event = stripe.Webhook.construct_event(payload, signature, secret)
    except Exception:
        return {"error": "signature invalide"}, 400

    event_id = event["id"]
    event_type = event["type"]
    data = event["data"]["object"]
    with get_db(current_app.config["DATABASE_PATH"]) as db:
        try:
            db.execute("INSERT INTO stripe_events(event_id,event_type) VALUES(?,?)", (event_id, event_type))
        except Exception:
            # Stripe retries are expected; do not process the same event twice.
            return {"received": True, "duplicate": True}, 200

        if event_type == "checkout.session.completed":
            metadata = data.get("metadata", {})
            user_id = metadata.get("user_id") or data.get("client_reference_id")
            if user_id and data.get("customer"):
                db.execute("UPDATE users SET stripe_customer_id=?, trial_started_at=COALESCE(trial_started_at,CURRENT_TIMESTAMP), updated_at=CURRENT_TIMESTAMP WHERE id=?", (data["customer"], user_id))

        elif event_type in {"customer.subscription.created", "customer.subscription.updated"}:
            metadata = data.get("metadata", {})
            user_id = metadata.get("user_id")
            plan = metadata.get("plan", "free")
            if user_id and plan in {"pro", "ultra"}:
                db.execute(
                    "UPDATE users SET plan=?, subscription_status=?, stripe_customer_id=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (plan, data.get("status", "active"), data.get("customer"), user_id),
                )

        elif event_type == "customer.subscription.deleted":
            customer = data.get("customer")
            db.execute(
                "UPDATE users SET plan='free', subscription_status='canceled', updated_at=CURRENT_TIMESTAMP WHERE stripe_customer_id=?",
                (customer,),
            )

        elif event_type == "invoice.payment_failed":
            customer = data.get("customer")
            db.execute(
                "UPDATE users SET subscription_status='past_due', updated_at=CURRENT_TIMESTAMP WHERE stripe_customer_id=?",
                (customer,),
            )

        db.commit()
    return {"received": True}, 200
