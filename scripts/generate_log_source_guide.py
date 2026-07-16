from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


OUTPUT = Path(__file__).resolve().parents[1] / "docs" / "Panduan_Sumber_Log_TraceLens.pdf"


def build() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    document = SimpleDocTemplate(str(OUTPUT), pagesize=A4, leftMargin=17*mm, rightMargin=17*mm,
                                 topMargin=16*mm, bottomMargin=16*mm,
                                 title="Panduan Sumber Log TraceLens AI")
    story = [Paragraph("Panduan Sumber Log untuk TraceLens AI", styles["Title"]),
             Paragraph("Gunakan hanya log milik sendiri atau sistem yang memang Anda berwenang investigasi. Jangan mengambil log dari perangkat, akun, atau server pihak lain tanpa izin.", styles["BodyText"]),
             Spacer(1, 4*mm), Paragraph("Format yang langsung didukung", styles["Heading2"])]
    supported = [
        ["Sumber", "Lokasi / cara memperoleh", "Format"],
        ["Linux SSH/auth", "/var/log/auth.log (Ubuntu/Debian) atau /var/log/secure (RHEL/CentOS)", "Plain text"],
        ["Linux system", "/var/log/syslog atau /var/log/messages", "Plain text"],
        ["Nginx", "/var/log/nginx/access.log dan /var/log/nginx/error.log", "Access log"],
        ["Apache", "/var/log/apache2/access.log atau /var/log/httpd/access_log", "Access log"],
        ["Aplikasi sendiri", "Export logger aplikasi dengan timestamp, level, message, user, IP, action, outcome", "CSV/JSONL"],
        ["Docker", "docker logs NAMA_CONTAINER > container.log; parser khusus Docker belum tersedia", "Perlu normalisasi"],
        ["Windows", "Event Viewer / Get-WinEvent; EVTX belum didukung langsung", "Konversi JSON/CSV"],
    ]
    table = Table(supported, repeatRows=1, colWidths=[31*mm, 104*mm, 35*mm])
    table.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.HexColor("#17365D")),
                               ("TEXTCOLOR", (0,0), (-1,0), colors.white),
                               ("GRID", (0,0), (-1,-1), .35, colors.grey),
                               ("VALIGN", (0,0), (-1,-1), "TOP"),
                               ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
                               ("FONTSIZE", (0,0), (-1,-1), 8),
                               ("LEADING", (0,0), (-1,-1), 10),
                               ("PADDING", (0,0), (-1,-1), 5)]))
    story.extend([table, Spacer(1, 5*mm), Paragraph("Perintah pengambilan contoh", styles["Heading2"]),
                  Paragraph("Linux: sudo cp /var/log/auth.log ./auth-copy.log", styles["Code"]),
                  Paragraph("Nginx: sudo cp /var/log/nginx/access.log ./nginx-access.log", styles["Code"]),
                  Paragraph("Docker: docker logs --timestamps NAMA_CONTAINER > container.log", styles["Code"]),
                  Paragraph("Windows PowerShell: Get-WinEvent -LogName Security -MaxEvents 500 | Select TimeCreated,Id,LevelDisplayName,Message | Export-Csv security-events.csv -NoTypeInformation", styles["Code"]),
                  Spacer(1, 4*mm), Paragraph("Sumber data latihan legal", styles["Heading2"]),
                  Paragraph("1. Folder samples pada repository TraceLens. 2. Log dari VM/lab milik sendiri. 3. Dataset publik seperti Loghub, HDFS, BGL, Apache, OpenSSH, dan Blue Team Labs yang lisensinya mengizinkan penggunaan. 4. Log sintetis yang dibuat khusus untuk pengujian parser dan agent.", styles["BodyText"]),
                  Paragraph("Catatan: dataset publik dapat memerlukan penyesuaian format. TraceLens saat ini langsung mendukung Linux auth/syslog, Nginx/Apache combined access log, JSON/JSONL generik, dan CSV aplikasi generik.", styles["BodyText"]),
                  Spacer(1, 4*mm), Paragraph("Cara membuat PDF investigasi", styles["Heading2"]),
                  Paragraph("Jalankan TraceLens, buat case, unggah log, tunggu status parsed, buka Findings & Report, lalu pilih Unduh PDF Investigasi. Backend akan memeriksa SHA-256 evidence sebelum membuat PDF.", styles["BodyText"]),
                  Spacer(1, 4*mm), Paragraph("Checklist sebelum upload", styles["Heading2"]),
                  Paragraph("Pastikan file UTF-8, ukuran tidak melebihi batas aplikasi, tidak mengandung token/password yang tidak perlu, timestamp dapat dipahami, dan Anda memiliki izin untuk memproses data tersebut.", styles["BodyText"])])
    document.build(story)


if __name__ == "__main__":
    build()
    print(OUTPUT)
