from flask import Flask, render_template, request, send_file, redirect, url_for, session, flash, jsonify
from functools import wraps
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_CENTER
import psycopg2
import psycopg2.extras
import os
import uuid
import stripe
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "angola-ticket-secret-2025")

# === STRIPE ===
stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "")

# === DIRECTÓRIO DE BILHETES ===
TICKETS_DIR = "tickets"
os.makedirs(TICKETS_DIR, exist_ok=True)


# ============================================================
# BASE DE DADOS PostgreSQL
# ============================================================
def get_db():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "ticket_angola"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", ""),
        cursor_factory=psycopg2.extras.RealDictCursor
    )


def init_db():
    """Cria as tabelas se não existirem."""
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            id SERIAL PRIMARY KEY,
            username VARCHAR(80) UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id SERIAL PRIMARY KEY,
            title VARCHAR(200) NOT NULL,
            description TEXT,
            date VARCHAR(80) NOT NULL,
            time VARCHAR(20) NOT NULL,
            location VARCHAR(200) NOT NULL,
            price INTEGER NOT NULL,
            category VARCHAR(80) NOT NULL,
            available INTEGER DEFAULT 100,
            image_icon VARCHAR(10) DEFAULT '🎟',
            active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT NOW()
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS purchases (
            id SERIAL PRIMARY KEY,
            ticket_number VARCHAR(30) UNIQUE NOT NULL,
            event_id INTEGER REFERENCES events(id),
            customer_name VARCHAR(200) NOT NULL,
            customer_email VARCHAR(200) NOT NULL,
            amount INTEGER NOT NULL,
            currency VARCHAR(10) DEFAULT 'AOA',
            payment_status VARCHAR(30) DEFAULT 'pending',
            stripe_payment_intent VARCHAR(200),
            pdf_filename VARCHAR(200),
            created_at TIMESTAMP DEFAULT NOW()
        );
    """)

    # Admin padrão (admin / admin123) - muda a senha depois!
    cur.execute("SELECT id FROM admins WHERE username = 'admin'")
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO admins (username, password_hash) VALUES (%s, %s)",
            ("admin", generate_password_hash("admin123"))
        )

    # Eventos de exemplo
    cur.execute("SELECT COUNT(*) as c FROM events")
    row = cur.fetchone()
    if row["c"] == 0:
        sample_events = [
            ("Festival de Música Luanda 2025", "O maior festival de música de Angola com artistas nacionais e internacionais.",
             "15 de Junho, 2025", "19:00", "Estádio da Cidadela, Luanda", 500000, "Música", 250, "🎵"),
            ("Conferência Tech Angola 2025", "Conferência sobre inovação tecnológica e transformação digital em África.",
             "22 de Junho, 2025", "09:00", "Centro de Convenções, Luanda", 1500000, "Tecnologia", 100, "💻"),
            ("Exposição de Arte Contemporânea", "Uma exposição única com obras de artistas angolanos e africanos.",
             "1 de Julho, 2025", "10:00", "Museu Nacional de Angola", 250000, "Arte", 500, "🎨"),
            ("Jogo de Futebol: Petro vs Sagrada", "O clássico do futebol angolano.",
             "5 de Julho, 2025", "16:00", "Estádio 11 de Novembro", 300000, "Desporto", 1200, "⚽"),
            ("Peça de Teatro: Alma Africana", "Uma peça emocionante sobre a história e cultura de África.",
             "12 de Julho, 2025", "20:00", "Teatro Nacional de Angola", 400000, "Teatro", 80, "🎭"),
            ("Workshop de Fotografia Urbana", "Aprenda fotografia urbana com profissionais em Luanda.",
             "19 de Julho, 2025", "08:00", "Ilha de Luanda", 800000, "Workshop", 30, "📷"),
        ]
        for ev in sample_events:
            cur.execute("""
                INSERT INTO events (title, description, date, time, location, price, category, available, image_icon)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, ev)

    conn.commit()
    cur.close()
    conn.close()
    print("✅ Base de dados inicializada.")


# ============================================================
# HELPERS
# ============================================================
def format_kz(amount):
    """Formata valor em Kwanza (amount em centavos AOA)."""
    return f"{amount:,.0f} Kz".replace(",", ".")


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin_id"):
            flash("Faça login para aceder ao painel.", "error")
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated


# ============================================================
# GERAÇÃO DE PDF
# ============================================================
def generate_ticket_pdf(customer_name, customer_email, event, ticket_number):
    filename = f"bilhete_{ticket_number}.pdf"
    filepath = os.path.join(TICKETS_DIR, filename)

    doc = SimpleDocTemplate(filepath, pagesize=A4,
                            rightMargin=2*cm, leftMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    elements = []
    styles = getSampleStyleSheet()

    cor_gold = colors.HexColor("#C8A951")
    cor_dark = colors.HexColor("#1A1A2E")
    cor_gray = colors.HexColor("#F5F5F5")

    def st(name, **kw):
        return ParagraphStyle(name, parent=styles['Normal'], **kw)

    # Cabeçalho
    header = Table([[Paragraph("🎟 TICKET ANGOLA", st('h', fontSize=26, textColor=cor_gold,
                                                       alignment=TA_CENTER, fontName='Helvetica-Bold'))],
                    [Paragraph("BILHETE OFICIAL DE ENTRADA", st('s', fontSize=11, textColor=colors.white,
                                                                 alignment=TA_CENTER))]], colWidths=[17*cm])
    header.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), cor_dark),
        ('PADDING', (0, 0), (-1, -1), 16),
    ]))
    elements.append(header)
    elements.append(Spacer(1, 0.4*cm))

    # Número do bilhete
    num = Table([[Paragraph(f"Nº {ticket_number}", st('n', fontSize=13, textColor=cor_gold,
                                                       alignment=TA_CENTER, fontName='Helvetica-Bold'))]], colWidths=[17*cm])
    num.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#F9F3E3")),
        ('BORDER', (0, 0), (-1, -1), 1.5, cor_gold),
        ('PADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(num)
    elements.append(Spacer(1, 0.4*cm))

    # Evento
    elements.append(Paragraph("EVENTO", st('lbl', fontSize=8, textColor=colors.HexColor("#888"),
                                            fontName='Helvetica-Bold')))
    elements.append(Paragraph(event["title"], st('ev', fontSize=18, textColor=cor_dark, fontName='Helvetica-Bold')))
    elements.append(Paragraph(event["description"], st('desc', fontSize=10, textColor=colors.HexColor("#666"))))
    elements.append(Spacer(1, 0.3*cm))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#DDD")))
    elements.append(Spacer(1, 0.3*cm))

    # Detalhes
    price_str = format_kz(event["price"])
    det = Table([[
        Table([[Paragraph("📅 DATA", st('l', fontSize=8, textColor=colors.HexColor("#888"), fontName='Helvetica-Bold'))],
               [Paragraph(event["date"], st('v', fontSize=12, fontName='Helvetica-Bold'))]], colWidths=[8*cm]),
        Table([[Paragraph("⏰ HORA", st('l2', fontSize=8, textColor=colors.HexColor("#888"), fontName='Helvetica-Bold'))],
               [Paragraph(event["time"], st('v2', fontSize=12, fontName='Helvetica-Bold'))]], colWidths=[8*cm]),
    ], [
        Table([[Paragraph("📍 LOCAL", st('l3', fontSize=8, textColor=colors.HexColor("#888"), fontName='Helvetica-Bold'))],
               [Paragraph(event["location"], st('v3', fontSize=12, fontName='Helvetica-Bold'))]], colWidths=[8*cm]),
        Table([[Paragraph("💰 PREÇO", st('l4', fontSize=8, textColor=colors.HexColor("#888"), fontName='Helvetica-Bold'))],
               [Paragraph(price_str, st('v4', fontSize=12, fontName='Helvetica-Bold'))]], colWidths=[8*cm]),
    ]], colWidths=[8.5*cm, 8.5*cm])
    det.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), cor_gray),
        ('PADDING', (0, 0), (-1, -1), 12),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#DDD")),
    ]))
    elements.append(det)
    elements.append(Spacer(1, 0.4*cm))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#DDD")))
    elements.append(Spacer(1, 0.3*cm))

    # Cliente
    cli = Table([[
        Table([[Paragraph("👤 NOME", st('cl', fontSize=8, textColor=colors.HexColor("#888"), fontName='Helvetica-Bold'))],
               [Paragraph(customer_name, st('cv', fontSize=12, fontName='Helvetica-Bold'))]], colWidths=[8*cm]),
        Table([[Paragraph("📧 EMAIL", st('cl2', fontSize=8, textColor=colors.HexColor("#888"), fontName='Helvetica-Bold'))],
               [Paragraph(customer_email, st('cv2', fontSize=12, fontName='Helvetica-Bold'))]], colWidths=[8*cm]),
    ]], colWidths=[8.5*cm, 8.5*cm])
    cli.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), cor_gray),
        ('PADDING', (0, 0), (-1, -1), 12),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#DDD")),
    ]))
    elements.append(cli)
    elements.append(Spacer(1, 0.4*cm))

    agora = datetime.now().strftime("%d/%m/%Y às %H:%M")
    elements.append(Paragraph(f"Emitido em: {agora} · Pagamento confirmado ✓",
                               st('em', fontSize=9, textColor=colors.HexColor("#999"), alignment=TA_CENTER)))
    elements.append(Spacer(1, 0.3*cm))

    footer = Table([[Paragraph(
        "Este bilhete é válido para uma entrada. Apresente na entrada do evento. Ticket Angola © 2025",
        st('ft', fontSize=8, textColor=colors.white, alignment=TA_CENTER))]], colWidths=[17*cm])
    footer.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), cor_dark),
        ('PADDING', (0, 0), (-1, -1), 12),
    ]))
    elements.append(footer)

    doc.build(elements)
    return filepath, filename


# ============================================================
# ROTAS PÚBLICAS
# ============================================================
@app.route("/")
def index():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM events WHERE active = TRUE ORDER BY id")
    events = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("index.html", events=events)


@app.route("/evento/<int:event_id>")
def evento(event_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM events WHERE id = %s AND active = TRUE", (event_id,))
    event = cur.fetchone()
    cur.close()
    conn.close()
    if not event:
        return redirect(url_for("index"))
    return render_template("event_detail.html", event=event,
                           stripe_key=STRIPE_PUBLISHABLE_KEY)


@app.route("/criar-pagamento/<int:event_id>", methods=["POST"])
def criar_pagamento(event_id):
    """Cria um PaymentIntent no Stripe."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM events WHERE id = %s AND active = TRUE", (event_id,))
    event = cur.fetchone()
    cur.close()
    conn.close()

    if not event:
        return jsonify({"error": "Evento não encontrado"}), 404

    customer_name = request.json.get("customer_name", "").strip()
    customer_email = request.json.get("customer_email", "").strip()

    if not customer_name or not customer_email:
        return jsonify({"error": "Nome e email são obrigatórios"}), 400

    if not stripe.api_key:
        # Modo de demonstração sem Stripe configurado
        ticket_number = f"TKT-{uuid.uuid4().hex[:8].upper()}"
        return jsonify({
            "demo_mode": True,
            "ticket_number": ticket_number,
            "customer_name": customer_name,
            "customer_email": customer_email,
            "event_id": event_id
        })

    try:
        intent = stripe.PaymentIntent.create(
            amount=event["price"],
            currency="aoa",
            metadata={
                "event_id": str(event_id),
                "customer_name": customer_name,
                "customer_email": customer_email,
            }
        )
        return jsonify({"client_secret": intent.client_secret, "payment_intent_id": intent.id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/confirmar-compra", methods=["POST"])
def confirmar_compra():
    """Confirma a compra após pagamento bem-sucedido."""
    data = request.json
    event_id = data.get("event_id")
    customer_name = data.get("customer_name", "").strip()
    customer_email = data.get("customer_email", "").strip()
    payment_intent_id = data.get("payment_intent_id", "")
    demo_mode = data.get("demo_mode", False)

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM events WHERE id = %s", (event_id,))
    event = cur.fetchone()

    if not event:
        cur.close()
        conn.close()
        return jsonify({"error": "Evento não encontrado"}), 404

    # Verificar pagamento real
    if not demo_mode and stripe.api_key:
        try:
            pi = stripe.PaymentIntent.retrieve(payment_intent_id)
            if pi.status != "succeeded":
                cur.close()
                conn.close()
                return jsonify({"error": "Pagamento não confirmado"}), 400
        except Exception as e:
            cur.close()
            conn.close()
            return jsonify({"error": str(e)}), 500

    ticket_number = data.get("ticket_number") or f"TKT-{uuid.uuid4().hex[:8].upper()}"
    _, filename = generate_ticket_pdf(customer_name, customer_email, dict(event), ticket_number)

    cur.execute("""
        INSERT INTO purchases (ticket_number, event_id, customer_name, customer_email,
                               amount, payment_status, stripe_payment_intent, pdf_filename)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, (ticket_number, event_id, customer_name, customer_email,
          event["price"], "paid" if not demo_mode else "demo",
          payment_intent_id, filename))

    cur.execute("UPDATE events SET available = available - 1 WHERE id = %s AND available > 0", (event_id,))
    conn.commit()
    cur.close()
    conn.close()

    return jsonify({
        "success": True,
        "ticket_number": ticket_number,
        "filename": filename,
        "customer_name": customer_name,
        "event_title": event["title"]
    })


@app.route("/sucesso")
def sucesso():
    ticket_number = request.args.get("ticket")
    filename = request.args.get("file")
    if not ticket_number:
        return redirect(url_for("index"))

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT p.*, e.title, e.date, e.time, e.location, e.image_icon, e.category
        FROM purchases p JOIN events e ON p.event_id = e.id
        WHERE p.ticket_number = %s
    """, (ticket_number,))
    purchase = cur.fetchone()
    cur.close()
    conn.close()

    if not purchase:
        return redirect(url_for("index"))
    return render_template("success.html", purchase=purchase)


@app.route("/download/<filename>")
def download(filename):
    filepath = os.path.join(TICKETS_DIR, filename)
    if not os.path.exists(filepath):
        flash("Ficheiro não encontrado.", "error")
        return redirect(url_for("index"))
    return send_file(filepath, as_attachment=True, download_name=filename)


# ============================================================
# ROTAS ADMIN
# ============================================================
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if session.get("admin_id"):
        return redirect(url_for("admin_dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM admins WHERE username = %s", (username,))
        admin = cur.fetchone()
        cur.close()
        conn.close()

        if admin and check_password_hash(admin["password_hash"], password):
            session["admin_id"] = admin["id"]
            session["admin_username"] = admin["username"]
            flash("Bem-vindo ao painel!", "success")
            return redirect(url_for("admin_dashboard"))
        else:
            flash("Credenciais inválidas.", "error")

    return render_template("admin/login.html")


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))


@app.route("/admin")
@login_required
def admin_dashboard():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) as total FROM purchases WHERE payment_status IN ('paid','demo')")
    total_vendas = cur.fetchone()["total"]

    cur.execute("SELECT COALESCE(SUM(amount), 0) as total FROM purchases WHERE payment_status IN ('paid','demo')")
    receita_total = cur.fetchone()["total"]

    cur.execute("SELECT COUNT(*) as total FROM events WHERE active = TRUE")
    total_eventos = cur.fetchone()["total"]

    cur.execute("""
        SELECT e.title, e.category, COUNT(p.id) as vendas, COALESCE(SUM(p.amount), 0) as receita
        FROM events e LEFT JOIN purchases p ON e.id = p.event_id AND p.payment_status IN ('paid','demo')
        WHERE e.active = TRUE
        GROUP BY e.id, e.title, e.category
        ORDER BY vendas DESC LIMIT 5
    """)
    top_events = cur.fetchall()

    cur.execute("""
        SELECT p.ticket_number, p.customer_name, p.customer_email, p.amount,
               p.payment_status, p.created_at, e.title as event_title
        FROM purchases p JOIN events e ON p.event_id = e.id
        ORDER BY p.created_at DESC LIMIT 10
    """)
    recent_purchases = cur.fetchall()

    cur.close()
    conn.close()

    return render_template("admin/dashboard.html",
                           total_vendas=total_vendas,
                           receita_total=receita_total,
                           total_eventos=total_eventos,
                           top_events=top_events,
                           recent_purchases=recent_purchases,
                           format_kz=format_kz)


@app.route("/admin/eventos")
@login_required
def admin_eventos():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT e.*, COUNT(p.id) as vendas
        FROM events e LEFT JOIN purchases p ON e.id = p.event_id AND p.payment_status IN ('paid','demo')
        GROUP BY e.id ORDER BY e.id DESC
    """)
    events = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("admin/events.html", events=events, format_kz=format_kz)


@app.route("/admin/eventos/novo", methods=["GET", "POST"])
@login_required
def admin_novo_evento():
    if request.method == "POST":
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO events (title, description, date, time, location, price, category, available, image_icon)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            request.form["title"], request.form["description"],
            request.form["date"], request.form["time"],
            request.form["location"], int(request.form["price"]),
            request.form["category"], int(request.form["available"]),
            request.form.get("image_icon", "🎟")
        ))
        conn.commit()
        cur.close()
        conn.close()
        flash("Evento criado com sucesso!", "success")
        return redirect(url_for("admin_eventos"))

    return render_template("admin/event_form.html", event=None)


@app.route("/admin/eventos/<int:event_id>/editar", methods=["GET", "POST"])
@login_required
def admin_editar_evento(event_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM events WHERE id = %s", (event_id,))
    event = cur.fetchone()

    if request.method == "POST":
        cur.execute("""
            UPDATE events SET title=%s, description=%s, date=%s, time=%s,
            location=%s, price=%s, category=%s, available=%s, image_icon=%s, active=%s
            WHERE id=%s
        """, (
            request.form["title"], request.form["description"],
            request.form["date"], request.form["time"],
            request.form["location"], int(request.form["price"]),
            request.form["category"], int(request.form["available"]),
            request.form.get("image_icon", "🎟"),
            "active" in request.form,
            event_id
        ))
        conn.commit()
        cur.close()
        conn.close()
        flash("Evento actualizado!", "success")
        return redirect(url_for("admin_eventos"))

    cur.close()
    conn.close()
    return render_template("admin/event_form.html", event=event)


@app.route("/admin/eventos/<int:event_id>/apagar", methods=["POST"])
@login_required
def admin_apagar_evento(event_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE events SET active = FALSE WHERE id = %s", (event_id,))
    conn.commit()
    cur.close()
    conn.close()
    flash("Evento desactivado.", "success")
    return redirect(url_for("admin_eventos"))


@app.route("/admin/compras")
@login_required
def admin_compras():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT p.*, e.title as event_title, e.date as event_date, e.category
        FROM purchases p JOIN events e ON p.event_id = e.id
        ORDER BY p.created_at DESC
    """)
    purchases = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("admin/purchases.html", purchases=purchases, format_kz=format_kz)


# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5001)
