import streamlit as st
import pandas as pd
import re
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
from datetime import datetime
import time
import io

# ページ設定
st.set_page_config(
    page_title="距離計算アプリ",
    page_icon="📍",
    layout="wide"
)

# タイトル
st.title("📍 地点から寺院までの距離計算アプリ")
st.markdown("---")

# サイドバー
with st.sidebar:
    st.header("📖 使い方")
    st.markdown("""
    1. **CSVファイルをアップロード**
       - 必須カラム: 「地点名」「住所」
    2. **自動処理**
       - 住所から緯度・経度を取得
       - 最寄りの寺院を検索
       - 距離を計算
    3. **結果をダウンロード**
       - CSVファイルとして保存可能
    """)
    
    st.header("📄 サンプルデータ")
    sample_data = pd.DataFrame({
        '地点名': ['A', 'B', 'C'],
        '住所': ['熊本県熊本市中央区坪井6丁目21', '愛知県豊明市沓掛町山新田２丁目４０−８', '岩手県陸前高田市竹駒町字下壺153']
    })
    csv_sample = sample_data.to_csv(index=False)
    st.download_button(
        label="サンプルCSVをダウンロード",
        data=csv_sample,
        file_name='sample_input.csv',
        mime='text/csv'
    )
    
    st.header("⚠️ 注意事項")
    st.markdown("""
    - ジオコーディングAPIの制限により、大量データの処理には時間がかかります
    - 1秒に1リクエストの制限があります
    """)

@st.cache_data
def load_temple_list():
    """寺院リストの読み込み（キャッシュ付き）"""
    try:
        temple_list_df = pd.read_csv("temple_list.csv")
        temple_list_df['緯度・経度'] = list(zip(temple_list_df['緯度'], temple_list_df['経度']))
        temple_list_df = temple_list_df.drop(['緯度', '経度'], axis=1)
        return temple_list_df
    except FileNotFoundError:
        st.error("temple_list.csvが見つかりません。")
        return None
    except Exception as e:
        st.error(f"寺院リストの読み込みエラー: {e}")
        return None

def geocode_address(address, geolocator):
    """住所から緯度・経度を取得"""
    # 数字より前の部分を検索住所として抽出
    match = re.search(r'\d', address)
    if match:
        search_address = address[:match.start()]
    else:
        search_address = address
    
    # ジオコーディング
    try:
        time.sleep(1)  # API制限対策
        location = geolocator.geocode(search_address)
        if location:
            return search_address, (location.latitude, location.longitude)
        else:
            # 区または町までに絞る
            simplified_address = re.sub(r'(区|町).*', r'\1', search_address)
            location = geolocator.geocode(simplified_address)
            if location:
                return simplified_address, (location.latitude, location.longitude)
            else:
                return search_address, None
    except Exception as e:
        st.warning(f"ジオコーディングエラー ({address}): {e}")
        return search_address, None

def find_nearest_temple(input_coords, temple_df):
    """入力座標に最も近い寺院を見つける"""
    if input_coords is None:
        return None, None
    
    min_distance = float('inf')
    nearest_temple_idx = None
    
    for idx, temple_coords in enumerate(temple_df['緯度・経度']):
        if temple_coords:
            distance = geodesic(input_coords, temple_coords).km
            if distance < min_distance:
                min_distance = distance
                nearest_temple_idx = idx
    
    if nearest_temple_idx is not None:
        return temple_df.iloc[nearest_temple_idx], min_distance
    return None, None

def process_data(input_df, temple_list_df):
    """データ処理のメイン関数"""
    geolocator = Nominatim(user_agent="distance_calculator_app")
    
    # 新規列を事前に作成
    input_df['検索住所'] = None
    input_df['緯度・経度'] = None
    
    # プログレスバー
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    total_rows = len(input_df)
    
    # ジオコーディング処理
    for index, row in input_df.iterrows():
        progress = (index + 1) / total_rows
        progress_bar.progress(progress)
        status_text.text(f"処理中: {index + 1}/{total_rows} - {row['地点名']} ({row['住所']})")
        
        search_address, coords = geocode_address(row['住所'], geolocator)
        input_df.at[index, '検索住所'] = search_address
        input_df.at[index, '緯度・経度'] = coords
    
    # 最寄りの寺院を検索
    status_text.text("最寄り寺院を検索中...")
    nearest_temple_data = []
    
    for index, row in input_df.iterrows():
        nearest_temple, distance = find_nearest_temple(row['緯度・経度'], temple_list_df)
        
        if nearest_temple is not None:
            temple_info = {
                '最寄り寺院名': nearest_temple['寺院名'],
                '最寄り寺院_住所': nearest_temple['住所'],
                '最寄り寺院_検索住所': nearest_temple['検索住所'],
                '最寄り寺院_緯度・経度': nearest_temple['緯度・経度'],
                '距離(km)': round(distance, 2)
            }
        else:
            temple_info = {
                '最寄り寺院名': None,
                '最寄り寺院_住所': None,
                '最寄り寺院_検索住所': None,
                '最寄り寺院_緯度・経度': None,
                '距離(km)': None
            }
        
        nearest_temple_data.append(temple_info)
    
    # データフレームに変換
    nearest_temple_df = pd.DataFrame(nearest_temple_data)
    
    # input_dfと横結合
    result_df = pd.concat([input_df, nearest_temple_df], axis=1)
    
    progress_bar.empty()
    status_text.empty()
    
    return result_df

# メインエリア
st.header("📤 CSVファイルをアップロード")

uploaded_file = st.file_uploader(
    "CSVファイルを選択してください", 
    type=['csv'],
    help="必須カラム: 地点名, 住所"
)

if uploaded_file is not None:
    try:
        # CSVファイルの読み込み
        input_df = pd.read_csv(uploaded_file)
        
        # カラム名の検証
        required_columns = ['地点名', '住所']
        missing_columns = [col for col in required_columns if col not in input_df.columns]
        
        if missing_columns:
            st.error(f"必須カラムが不足しています: {', '.join(missing_columns)}")
            st.stop()
        
        # アップロードされたデータのプレビュー
        st.subheader("📊 アップロードされたデータ")
        st.dataframe(input_df, use_container_width=True)
        
        # 寺院リストの読み込み
        temple_list_df = load_temple_list()
        
        if temple_list_df is None:
            st.stop()
        
        # 処理実行ボタン
        if st.button("🚀 距離計算を開始", type="primary"):
            with st.spinner("処理中..."):
                # データ処理
                result_df = process_data(input_df, temple_list_df)
                
                # セッションステートに結果を保存
                st.session_state['result_df'] = result_df
                
                # 成功メッセージ
                st.success("✅ 処理が完了しました！")
        
        # 結果の表示
        if 'result_df' in st.session_state:
            result_df = st.session_state['result_df']
            
            st.markdown("---")
            st.header("📈 処理結果")
            
            # サマリー統計
            col1, col2, col3, col4 = st.columns(4)
            
            # NaNを除外して統計を計算
            valid_distances = result_df['距離(km)'].dropna()
            
            with col1:
                st.metric("処理件数", f"{len(result_df)} 件")
            
            with col2:
                if len(valid_distances) > 0:
                    st.metric("平均距離", f"{valid_distances.mean():.2f} km")
                else:
                    st.metric("平均距離", "N/A")
            
            with col3:
                if len(valid_distances) > 0:
                    st.metric("最短距離", f"{valid_distances.min():.2f} km")
                else:
                    st.metric("最短距離", "N/A")
            
            with col4:
                if len(valid_distances) > 0:
                    st.metric("最長距離", f"{valid_distances.max():.2f} km")
                else:
                    st.metric("最長距離", "N/A")
            
            # 結果テーブル
            st.subheader("📋 詳細データ")
            st.dataframe(result_df, use_container_width=True)
            
            # ダウンロードボタン
            st.subheader("💾 結果のダウンロード")
            
            # タイムスタンプ付きファイル名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"result_{timestamp}.csv"
            
            # CSVデータの生成
            csv_buffer = io.StringIO()
            result_df.to_csv(csv_buffer, index=False)
            csv_data = csv_buffer.getvalue()
            
            st.download_button(
                label="📥 CSVファイルをダウンロード",
                data=csv_data,
                file_name=filename,
                mime='text/csv',
                type="primary"
            )
            
            # ジオコーディング失敗件数の表示
            failed_geocoding = result_df[result_df['緯度・経度'].isna()]
            if len(failed_geocoding) > 0:
                st.warning(f"⚠️ {len(failed_geocoding)}件の住所でジオコーディングに失敗しました")
                with st.expander("失敗した住所を表示"):
                    st.dataframe(failed_geocoding[['地点名', '住所']])
    
    except pd.errors.EmptyDataError:
        st.error("アップロードされたファイルが空です。")
    except Exception as e:
        st.error(f"ファイルの処理中にエラーが発生しました: {e}")
        st.exception(e)

else:
    # ファイルがアップロードされていない場合
    st.info("👈 左のサイドバーからサンプルデータをダウンロードして、お試しください。")
