import streamlit as st
import json
import qrcode
from io import BytesIO
from openai import OpenAI

st.set_page_config(page_title="Generatore Pagamenti QR", page_icon="💳", layout="centered")
st.title("💳 Generatore Multicanale QR Mediolanum/CA")

# Gestione API Key
key = st.secrets.get("REGOLO_API_KEY", "")
if not key:
    with st.sidebar:
        key = st.text_input("Inserisci API Key Regolo.ai", type="password")
client = OpenAI(base_url="https://api.regolo.ai/v1", api_key=key) if key else None

PROMPT_SISTEMA = (
    "Sei un esperto contabile. Analizza l'email e genera un JSON rigoroso con questi campi: "
    "tipo_pagamento (bonifico_sepa, bollettino_postale, postepay_standard, postepay_evolution), "
    "beneficiario, importo (float), causale, iban, numero_conto_corrente_postale, "
    "codice_bollettino, numero_carta_postepay, codice_fiscale_destinatario. "
    "Se un dato manca, usa null. Non aggiungere commenti, solo JSON."
)


def analizza(testo):
    if not client:
        st.error("Configura API Key")
        return None
    try:
        res = client.chat.completions.create(
            model="Llama-3.3-70B-Instruct",
            messages=[
                {"role": "system", "content": PROMPT_SISTEMA},
                {"role": "user", "content": testo},
            ],
            temperature=0.1,
        )
        content = res.choices[0].message.content.strip()
        # Strip markdown code fences (```json ... ``` or ``` ... ```)
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()
        return json.loads(content)
    except json.JSONDecodeError:
        raw = res.choices[0].message.content if res else "nessuna risposta"
        st.error(f"Risposta non valida dal modello:\n{raw[:300]}")
        return None
    except Exception as e:
        st.error(f"Errore API: {type(e).__name__}: {e}")
        return None


def gen_qr(dati):
    t = dati["tipo_pagamento"]
    i = float(dati.get("importo") or 0)

    if t in ["bonifico_sepa", "postepay_evolution"]:
        # Formato EPC/GiroCode per SEPA
        data = (
            f"BCD\n002\n1\nSCT\n\n"
            f"{dati.get('beneficiario', '')}\n"
            f"{(dati.get('iban') or '').replace(' ', '')}\n"
            f"EUR{i:.2f}\n\n\n"
            f"{dati.get('causale', '')}\n"
        )
    elif t == "bollettino_postale":
        data = (
            f"<{dati.get('numero_conto_corrente_postale', '')}>"
            f"{int(i * 100)}"
            f"<{(dati.get('causale') or '')[:18]}>"
            f"{dati.get('codice_fiscale_destinatario', '')}"
            f"<{dati.get('codice_bollettino', '896')}>"
        )
    else:
        # Postepay standard
        data = (
            f"RICARICA POSTEPAY: {dati.get('numero_carta_postepay', '')} | "
            f"Imp: {i}€ | Ben: {dati.get('beneficiario', '')}"
        )

    qr = qrcode.QRCode(box_size=10, border=4)
    qr.add_data(data)
    qr.make(fit=True)
    buf = BytesIO()
    qr.make_image(fill_color="black", back_color="white").save(buf, format="PNG")
    return buf.getvalue()


# Interfaccia
testo = st.text_area("Incolla qui il contenuto dell'email:", height=150)
if st.button("Analizza"):
    with st.spinner("Analisi in corso..."):
        ris = analizza(testo)
    if ris:
        st.session_state["dati"] = ris

if "dati" in st.session_state:
    d = st.session_state["dati"]
    st.subheader("Verifica Dati")
    d["beneficiario"] = st.text_input("Beneficiario", d.get("beneficiario") or "")
    d["iban"] = st.text_input("IBAN", d.get("iban") or "")
    d["importo"] = st.number_input("Importo", value=float(d.get("importo") or 0))
    d["causale"] = st.text_input("Causale", d.get("causale") or "")

    if st.button("Genera QR Code"):
        st.image(gen_qr(d), use_container_width=True)
        st.toast("Elaborazione completata!")
        st.success("QR generato! Inquadralo con la tua banca.")
