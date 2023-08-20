from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup


# えひめ医療情報ネット
base_url = "http://www.qq.pref.ehime.jp/qq38/WP0805/RP080501BL"

# 今治市地区を選択

payload = {
    "_blockCd": "",
    "forward_next": "",
    "torinBlockDetailInfo.torinBlockDetail[0].blockCheckFlg": "0",
    "torinBlockDetailInfo.torinBlockDetail[1].blockCheckFlg": "0",
    "torinBlockDetailInfo.torinBlockDetail[2].blockCheckFlg": "0",
    "torinBlockDetailInfo.torinBlockDetail[3].blockCheckFlg": "1",
    "torinBlockDetailInfo.torinBlockDetail[4].blockCheckFlg": "0",
    "torinBlockDetailInfo.torinBlockDetail[5].blockCheckFlg": "0",
    "torinBlockDetailInfo.torinBlockDetail[6].blockCheckFlg": "0",
    "torinBlockDetailInfo.torinBlockDetail[7].blockCheckFlg": "0",
    "torinBlockDetailInfo.torinBlockDetail[8].blockCheckFlg": "0",
    "torinBlockDetailInfo.torinBlockDetail[9].blockCheckFlg": "0",
    "torinBlockDetailInfo.torinBlockDetail[10].blockCheckFlg": "0",
    "torinBlockDetailInfo.torinBlockDetail[11].blockCheckFlg": "0",
    "torinBlockDetailInfo.torinBlockDetail[12].blockCheckFlg": "0",
}

# 当番医の今治市地区のページにアクセス

with requests.Session() as s:
    r = s.get(base_url)

    soup = BeautifulSoup(r.content, "html.parser")

    # トークンを取得
    token = soup.find("input", attrs={"name": "_csrf"}).get("value")

    # トークンをセット
    payload["_csrf"] = token

    # URL生成
    url = urljoin(
        base_url, soup.find("form", attrs={"id": "_wp0805Form"}).get("action")
    )

    # データ送信
    r = s.post(url, data=payload)

# スクレイピング

soup = BeautifulSoup(r.content, "html.parser")

tables = soup.find_all("table", class_="comTblGyoumuCommon", summary="検索結果一覧を表示しています。")

result = []

for table in tables:
    # 日付取得
    date, week = table.td.get_text(strip=True).split()

    # 救急病院のリスト作成
    for trs in table.find_all("tr", id=[1, 2, 3]):
        data = (
            [None]
            + [list(td.stripped_strings) for td in trs.find_all("td", recursive=False)]
            + [date, week]
        )
        result.append(data[-5:])

# データラングリング

df0 = (
    pd.DataFrame(result)
    .fillna(method="ffill")
    .set_axis(["医療機関情報", "診療科目", "外来受付時間", "日付", "week"], axis=1)
)

df0

# 列名順番
col = [
    "date",
    "week",
    "name",
    "address",
    "tel",
    "night_tel",
    "type",
    "time_1st",
    "time_2nd",
    "date_week",
    "time",
    "class",
    "lat",
    "lon",
    "navi",
]

# 日付変換
df0["date"] = pd.to_datetime(
    df0["日付"]
    .str.extract("(?P<year>\d{4})年(?P<month>\d{1,2})月(?P<day>\d{1,2})日")
    .astype(int)
)

df0["date_week"] = df0["日付"].str.cat(df0["week"], sep=" ")

# 医療機関情報
df0[["name", "address", "tel", "night_tel"]] = (
    df0["医療機関情報"].apply(pd.Series).drop([2, 4], axis=1)
)

# 医療科目
df0["type"] = df0["診療科目"].apply(pd.Series)

# 外来受付時間
df0[["time_1st", "time_2nd"]] = df0["外来受付時間"].apply(pd.Series)

df1 = df0.reindex(columns=col[:10]).copy()

df1.dtypes

# ソート用

# 診療科目
df1["診療科目ID"] = df1["type"].map({"指定なし": 0, "内科": 2, "小児科": 7})

# 外科系
df1["診療科目ID"].mask(df1["type"].str.contains("外科", na=False), 1, inplace=True)

# 内科系
df1["診療科目ID"].mask(df1["type"].str.contains("内科", na=False), 2, inplace=True)


# 島しょ部
simanami_flag = df1["address"].str.contains("吉海町|宮窪町|伯方町|上浦町|大三島町|関前", na=False)

df1["診療科目ID"].mask(simanami_flag, 9, inplace=True)

df1["type"].mask(simanami_flag, "島しょ部", inplace=True)

# その他
df1["診療科目ID"] = df1["診療科目ID"].fillna(8).astype(int)

# 開始時間
df1["開始時間"] = pd.to_timedelta(df1["time_1st"].str.split("～").str[0] + ":00")

df1["time"] = (
    df1["time_1st"].str.cat(df1["time_2nd"], na_rep="", sep=" / ").str.strip(" /")
)

# 現在
dt_now = pd.Timestamp.now(tz="Asia/Tokyo").tz_localize(None)

df1["class"] = None

df1.loc[df1["date"].dt.date < dt_now.date(), "class"] = "yesterday"

df1.loc[
    (df1["date"].dt.date == dt_now.date()) & (df1["診療科目ID"] != 0), "class"
] = "other"

df2 = (
    df1.sort_values(by=["date", "診療科目ID", "開始時間"])
    .reindex(columns=col[:-3])
    .reset_index(drop=True)
    .copy()
)

df2

# 位置情報付与

csv_url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQijVNaEWw2giRgQJSaBsJJAzdzhR47dQ3NU1eBj9lSCv8-bZnUjD6e2CFUV_YqQqs-xsdKBAWM8LOb/pub?gid=0&single=true&output=csv"

df3 = pd.read_csv(csv_url)

# ルート案内のURLを生成
df3["navi"] = "https://www.google.com/maps/dir/?api=1&destination=" + df3["lat"].astype(
    str
).str.cat(df3["lon"].astype(str), sep=",")

# latまたはlonが欠損の場合は、naviも欠損にする
df3["navi"].mask(df3[["lat", "lon"]].isna().any(axis=1), inplace=True)

# 医療機関と位置情報を結合する
df_hosp = pd.merge(df2, df3, on="name", how="left").reindex(columns=col)

df_hosp

df_hosp.to_csv("latest.csv", index=False)
