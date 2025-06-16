# ==============================================================================
# PHẦN 1: TÁI SỬ DỤNG GẦN NHƯ TOÀN BỘ CODE CŨ CỦA BẠN
# ==============================================================================
import pandas as pd
import requests
import io
import html
from datetime import datetime
from flask import Flask, jsonify, render_template, request, Response
import io

# --- CÁC HÀM GỌI API (Giữ nguyên) ---
def execute_sql_query(function_name, sql_query):
    """Gửi yêu cầu API và trả về phản hồi thô dưới dạng text."""
    url = 'http://14.161.13.194:8065/ws_Banggia.asmx'
    soap_body_template = """<?xml version="1.0" encoding="utf-8"?>
    <s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
      <s:Body><{function_name} xmlns="http://tempuri.org/"><m_sql>{sql_command}</m_sql><m_function_name /><m_user>BENTHANH@194</m_user></{function_name}></s:Body>
    </s:Envelope>"""

    escaped_sql_command = html.escape(sql_query)
    soap_body = soap_body_template.format(function_name=function_name, sql_command=escaped_sql_command)
    headers = {
        'Content-Type': 'text/xml; charset=utf-8',
        'SOAPAction': f'"http://tempuri.org/{function_name}"',
        'Host': '14.161.13.194:8065',
    }
    try:
        response = requests.post(url, data=soap_body.encode('utf-8'), headers=headers, timeout=180)
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException as e:
        print(f"Lỗi API khi gọi hàm {function_name}: {e}")
        return f"<error>Lỗi kết nối API: {e}</error>"


def fetch_dataframe(function_name, sql_query, dtypes=None):
    """Thực hiện gọi API và chuyển kết quả XML thành Pandas DataFrame."""
    print(f"Đang thực thi API: {function_name} với query:\n{sql_query}\n")
    xml_response = execute_sql_query(function_name, sql_query)
    if xml_response.startswith("<error>"):
        raise ConnectionError(xml_response)
    try:
        df = pd.read_xml(io.StringIO(xml_response), xpath=".//diffgr:diffgram/NewDataSet/Table1",
                         namespaces={"diffgr": "urn:schemas-microsoft-com:xml-diffgram-v1"},
                         dtype=dtypes)
        return df
    except ValueError:
        return pd.DataFrame()

# --- LỚP CONFIG (Giữ nguyên) ---
class Config:
    DB_TABLE_UNC = "[ThuUNC]"
    DB_TABLE_HOADON = "[hoadon]"
    COLUMN_MAPPING_UNC = {"NgayThu": "NgayThu", "SoBK": "SoBK"}
    COLUMN_MAPPING_HOADON = {"TONGCONG_BD": "TONGCONG_BD", "NGAYGIAI": "NGAYGIAI", "Ky": "Ky", "Nam": "Nam"}
    BANK_DICT = {
        '0': 'AGRIBANK', 'A': 'ACB', 'Ai': 'AIRPAY', 'B': 'BIDV', 'BP': 'AGRIBANK',
        'D': 'DONGA', 'Da': 'DONGA', 'E': 'EXIMBANK', 'K': 'KHO BAC', 'M': 'MOMO',
        'OC': 'OCEANBANK', 'P': 'PAYOO', 'Pv': 'PAYOO', 'Pd': 'PAYOO', 'Q': 'QUẦY',
        'V': 'VIETTEL', 'VC': 'VIETCOMBANK', 'VT': 'VIETTIN', 'Vn': 'VNPAY', 'Z': 'ZALOPAY'
    }
    PATTERN = r"Ai|Z|Pv|VT|VC|Vn|Pd|Da|E|^A|BP|V|^M|B|D|Q|P|K|OC|SG|B"

# --- CÁC HÀM XỬ LÝ DỮ LIỆU (Giữ nguyên, chỉ bỏ phần liên quan đến PyQt) ---
def get_main_data(start_date_sql_str, end_date_sql_str):
    config = Config()
    sql_col_ngaythu_actual = config.COLUMN_MAPPING_UNC["NgayThu"]
    sql_col_sobk_actual = config.COLUMN_MAPPING_UNC["SoBK"]
    query_string = f"""
    SELECT [{sql_col_sobk_actual}] AS SoBK, (ISNULL([Giaban], 0) + ISNULL([Thue], 0) + ISNULL([Phi], 0) + ISNULL([ThueDVTN], 0)) AS TienBT
    FROM {config.DB_TABLE_UNC}
    WHERE CAST([{sql_col_ngaythu_actual}] AS DATE) BETWEEN '{start_date_sql_str}' AND '{end_date_sql_str}'
    """
    df_filtered = fetch_dataframe('f_Select_SQL_Thutien', query_string)
    if df_filtered.empty: return pd.DataFrame()
    df_filtered['Ngân Hàng'] = df_filtered['SoBK'].astype(str).str.extract(f'({config.PATTERN})')
    df_filtered['Ngân Hàng'] = df_filtered['Ngân Hàng'].map(config.BANK_DICT).fillna('AGRIBANK')
    df_group = df_filtered.groupby('Ngân Hàng').agg(TongDoanhThu=('TienBT', 'sum'), TongSoGiaoDich=('Ngân Hàng', 'size')).reset_index()
    total_tienbt = df_filtered['TienBT'].sum()
    total_sogiaodich = len(df_filtered)
    df_group['Tỷ lệ (%)'] = (df_group['TongDoanhThu'] / total_tienbt * 100) if total_tienbt > 0 else 0.0
    df_group = df_group.sort_values(by='Ngân Hàng', ascending=True)
    df_display = df_group[['Ngân Hàng', 'TongDoanhThu', 'TongSoGiaoDich', 'Tỷ lệ (%)']].copy()
    df_display.rename(columns={'TongDoanhThu': 'Tổng cộng', 'TongSoGiaoDich': 'Tổng hoá đơn'}, inplace=True)
    df_total = pd.DataFrame({'Ngân Hàng': ['Tổng cộng'], 'Tổng cộng': [total_tienbt], 'Tổng hoá đơn': [total_sogiaodich], 'Tỷ lệ (%)': [100.0]})
    return pd.concat([df_display, df_total], ignore_index=True)

def get_analysis_data():
    config = Config()
    current_date = datetime.now()
    current_period = current_date.month
    current_year = current_date.year
    col_map = config.COLUMN_MAPPING_HOADON
    col_tongcong, col_ngaygiai, col_ky, col_nam = (col_map["TONGCONG_BD"], col_map["NGAYGIAI"], col_map["Ky"], col_map["Nam"])
    query = f"""
        SELECT
            SUM(CASE WHEN [{col_nam}] < {current_year} THEN [{col_tongcong}] ELSE 0 END) AS TonNamCu,
            SUM(CASE WHEN [{col_nam}] = {current_year} AND [{col_ky}] < {current_period} THEN [{col_tongcong}] ELSE 0 END) AS TonLuyKeNamHienTai,
            SUM(CASE WHEN [{col_nam}] = {current_year} AND [{col_ky}] = {current_period} THEN [{col_tongcong}] ELSE 0 END) AS TonKyHienTai,
            SUM([{col_tongcong}]) AS TonTatCa
        FROM {config.DB_TABLE_HOADON}
        WHERE [{col_ngaygiai}] IS NULL
    """
    df_result = fetch_dataframe('f_Select_SQL_Thutien', query)
    if not df_result.empty:
        result_row = df_result.iloc[0]
        # --- SỬA LỖI Ở ĐÂY: Thêm int() để ép kiểu ---
        results = {
            f"Tồn năm cũ": int(result_row['TonNamCu'] or 0),
            f"Tồn các kỳ năm {current_year}": int(result_row['TonLuyKeNamHienTai'] or 0),
            f"Tồn kỳ {current_period:02d}/{current_year}": int(result_row['TonKyHienTai'] or 0),
            "Tồn tất cả": int(result_row['TonTatCa'] or 0)
        }
        return results
    return None

# ==============================================================================
# PHẦN 2: XÂY DỰNG WEB SERVER VỚI FLASK
# ==============================================================================

# Tạo một đối tượng ứng dụng web Flask
app = Flask(__name__)

@app.route('/')
def home():
    """
    Phục vụ trang web chính (index.html).
    """
    return render_template('index.html')

# --- Định nghĩa các API Endpoint ---

@app.route('/api/main_data')
def api_main_data():
    """
    Endpoint cung cấp dữ liệu cho bảng chính.
    Giờ đây có thể nhận from_date và to_date từ URL.
    """
    # Lấy ngày hôm nay làm giá trị mặc định nếu không có tham số nào được cung cấp
    today_str = datetime.now().strftime('%Y-%m-%d')

    # Đọc tham số từ URL, ví dụ: /api/main_data?from_date=YYYY-MM-DD
    # request.args.get() sẽ lấy giá trị, nếu không có thì dùng giá trị mặc định (today_str)
    from_date = request.args.get('from_date', today_str)
    to_date = request.args.get('to_date', today_str)

    try:
        # Truyền ngày tháng đã nhận được vào hàm xử lý logic
        df = get_main_data(from_date, to_date)
        json_data = df.to_json(orient='records', force_ascii=False)
        return json_data, 200, {'Content-Type': 'application/json; charset=utf-8'}
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/analysis_data')
def api_analysis_data():
    """
    Endpoint cung cấp dữ liệu cho bảng phân tích.
    """
    try:
        data = get_analysis_data()
        if data:
            # Dữ liệu này đã là dictionary, dùng jsonify của Flask để chuyển thành JSON
            return jsonify(data)
        else:
            return jsonify({"error": "Không có dữ liệu phân tích"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/export_excel')
def export_to_excel():
    """
    Endpoint tạo file Excel từ dữ liệu được lọc và gửi về cho người dùng tải xuống.
    """
    today_str = datetime.now().strftime('%Y-%m-%d')
    from_date = request.args.get('from_date', today_str)
    to_date = request.args.get('to_date', today_str)

    try:
        # Lấy dữ liệu DataFrame giống hệt như cách lấy cho bảng chính
        df_to_export = get_main_data(from_date, to_date)

        # Tạo một bộ đệm trong bộ nhớ để lưu file Excel
        output_buffer = io.BytesIO()

        # Dùng Pandas để ghi DataFrame vào bộ đệm, định dạng là Excel
        # index=False để không ghi chỉ số của DataFrame vào file Excel
        df_to_export.to_excel(output_buffer, index=False, sheet_name='BaoCaoDoanhThu')

        # Di chuyển con trỏ về đầu bộ đệm
        output_buffer.seek(0)

        # Tạo một phản hồi HTTP đặc biệt để trình duyệt hiểu đây là một file cần tải xuống
        return Response(
            output_buffer,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment;filename=BaoCaoDoanhThu_{from_date}_den_{to_date}.xlsx"}
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- Chạy ứng dụng web ---
if __name__ == '__main__':
    # Chạy máy chủ web ở chế độ debug (sẽ tự khởi động lại khi có thay đổi)
    # host='0.0.0.0' để có thể truy cập từ các thiết bị khác trong cùng mạng (như iPhone của bạn)
    app.run(debug=True, host='0.0.0.0', port=5000)