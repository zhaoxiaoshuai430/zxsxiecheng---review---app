# -*- coding: utf-8 -*-
"""
🏨 酒店评论智能分析系统（支持预评分 + 文本提取混合模式）
"""

import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from collections import defaultdict
import jieba
import re
import base64
from io import BytesIO
import requests
import time

# ==================== 页面配置 ====================
st.set_page_config(page_title="酒店评论分析系统", layout="wide")

# ==================== 初始化 session_state ====================
if 'history' not in st.session_state:
    st.session_state.history = []

if 'hotel_name' not in st.session_state:
    st.session_state.hotel_name = "中油花园酒店"

if 'hotel_location' not in st.session_state:
    st.session_state.hotel_location = "市中心繁华地段"

# ==================== 工具函数：Excel 导出 ====================
def to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='原始数据')
    return output.getvalue()

# ==================== 中文分词与情感分析 ====================
# 自定义关键词库（可扩展）
TAG_KEYWORDS = {
    '位置': ['位置', '地段', '周边', '附近', '离', '靠近', '市中心', '地铁', '公交', '导航'],
    '交通': ['交通', '打车', '停车', '驾车', '机场', '车站', '接驳', '出租车', '网约车'],
    '早餐': ['早餐', '早饭', '餐饮', 'buffet', '餐食', '自助餐', '丰富', '种类'],
    '安静': ['安静', '噪音', '吵', '吵闹', '隔音', '清静', '安静房', '半夜', '安静'],
    '床舒适': ['床', '床垫', '睡感', '舒服', '舒不舒服', '软硬', '枕头', '被子'],
    '房间大小': ['房间小', '房间大', '空间', '拥挤', '宽敞', '面积', '局促', '紧凑'],
    '视野': ['视野', '景观', '江景', '海景', '窗景', '朝向', '夜景', 'view', '窗外'],
    '性价比': ['性价比', '价格', '划算', '贵', '便宜', '值', '物超所值', '贵不贵'],
    '前台': ['前台', '接待', 'check in', '入住办理', '退房', '接待员', '效率', '等待'],
    '网络': ['Wi-Fi', '网络', '信号', '上网', '网速', 'wifi', '无线', '连不上']
}

POSITIVE_WORDS = {'好', '棒', '赞', '满意', '不错', '推荐', '惊喜', '舒服', '完美', '贴心',
                  '干净', '方便', '快捷', '温馨', '柔软', '丰富', '齐全', '优质', '热情', '值得'}
NEGATIVE_WORDS = {'差', '糟', '烂', '坑', '差劲', '失望', '糟糕', '难用', '吵', '脏',
                  '贵', '偏', '慢', '不值', '问题', '敷衍', '拖延', '恶劣', '难闻'}

def preprocess(text):
    """文本预处理：去标点、分词"""
    text = re.sub(r'[^\u4e00-\u9fa5a-zA-Z]', '', str(text).lower())
    words = jieba.lcut(text)
    return [w for w in words if len(w) >= 2]

def get_sentiment_score(text):
    """情感分析打分"""
    words = preprocess(text)
    pos_count = sum(1 for w in words if w in POSITIVE_WORDS)
    neg_count = sum(1 for w in words if w in NEGATIVE_WORDS)
    total = pos_count + neg_count
    if total == 0:
        return 3.8  # 中性
    if pos_count > neg_count:
        return min(5.0, 4.5 + 0.5 * (pos_count / total))
    elif neg_count > pos_count:
        return max(1.0, 2.5 - 0.5 * (neg_count / total))
    else:
        return 3.8

def extract_tags_with_scores(comments):
    """从评论中提取维度得分"""
    tag_scores = defaultdict(list)
    for comment in comments.dropna():
        for tag, keywords in TAG_KEYWORDS.items():
            if any(kw in str(comment) for kw in keywords):
                score = get_sentiment_score(str(comment))
                tag_scores[tag].append(score)
    final_scores = {
        tag: round(sum(scores) / len(scores), 2)
        for tag, scores in tag_scores.items()
        if len(scores) > 0
    }
    return final_scores

# ==================== 优化建议库 ====================
SUGGESTIONS = {
    '位置': '优化导航信息，与周边商圈合作提供折扣弥补位置短板。',
    '交通': '提供免费接驳车或与打车平台合作，提升客人便利性。',
    '早餐': '丰富早餐品类，增加本地特色和健康选项，提升餐品温度。',
    '安静': '优化隔音设计，更换密封性更好的门窗，减少噪音干扰。',
    '床舒适': '升级床垫与床品材质，提供软硬两种枕头供客人选择。',
    '房间大小': '优化小房型空间布局，推出“大房型优先升级”优惠活动。',
    '视野': '定期清洁窗户与阳台，避免景观遮挡，拍摄高质量宣传图。',
    '性价比': '调整价格策略，推出不同时段优惠套餐，增加增值服务。',
    '前台': '缩短入住/退房等待时间，推行自助机或移动端办理。',
    '网络': '升级Wi-Fi带宽，确保全区域稳定覆盖，设置一键连接页面。'
}

# ==================== 通义千问 API 调用（可选）====================
def call_qwen_api(prompt, api_key, model="qwen-max"):
    url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    data = {
        "model": model,
        "input": {"messages": [{"role": "user", "content": prompt}]},
        "parameters": {"temperature": 0.7, "max_tokens": 512}
    }
    try:
        response = requests.post(url, headers=headers, json=data)
        result = response.json()
        return result['output']['text'].strip()
    except Exception as e:
        return f"❌ 调用失败：{str(e)}"

def generate_prompt(comment, hotel_name, location):
    return f"""
你是一家名为【{hotel_name}】的酒店客服，请以温暖、专业、真诚的口吻回复以下客人评论。
酒店位于：{location}，请结合地理位置适当提及。

评论内容：{comment}

要求：
1. 先感谢客人；
2. 若为好评，表达荣幸与欢迎再来；
3. 若为差评，诚恳道歉并说明改进方向；
4. 语言自然，避免模板化；
5. 不要使用“我们”、“您”等生硬称呼，可适度拟人化；
6. 限80字以内。

请直接输出回复内容：
"""

def truncate_to_word_count(text, max_words=60):
    words = text.split()
    return ' '.join(words[:max_words])

# ==================== 侧边栏配置 ====================
st.sidebar.title("🏨 酒店分析系统")
page = st.sidebar.radio("选择功能", [
    "📈 维度分析（混合模式）",
    "💬 智能评论回复"
])

st.sidebar.divider()
st.sidebar.subheader("⚙️ 酒店配置")
hotel_name = st.sidebar.text_input("酒店名称", st.session_state.hotel_name)
hotel_location = st.sidebar.text_input(
    "酒店位置描述",
    st.session_state.hotel_location,
    help="例如：市中心繁华地段、近地铁2号线湖滨站等"
)

api_key = st.sidebar.text_input("通义千问API密钥（可选）", type="password", help="用于智能回复")

if st.sidebar.button("💾 保存配置"):
    st.session_state.hotel_name = hotel_name.strip() or "未命名酒店"
    st.session_state.hotel_location = hotel_location.strip() or "该城市某处"
    st.sidebar.success("✅ 配置已保存")

# ==================== 主页面逻辑 ====================

# ============ 1. 维度分析（混合模式） ============
if page == "📈 维度分析（混合模式）":
    st.title("📈 酒店维度评分分析（混合模式）")
    st.markdown("""
    上传包含以下列的 Excel 文件：
    - `评论内容`（必填）
    - `设施`、`卫生`、`环境`、`服务`（数值型，1~5分）
    """)

    with st.expander("📄 示例格式"):
        st.dataframe(pd.DataFrame({
            '评论内容': ["房间干净，服务很好。", "设施较旧，但位置方便。"],
            '设施': [4.5, 3.8],
            '卫生': [4.8, 4.2],
            '环境': [4.6, 4.0],
            '服务': [4.7, 4.5]
        }))

    uploaded_file = st.file_uploader("上传 Excel 文件 (.xlsx)", type=["xlsx"])

    if uploaded_file:
        try:
            df = pd.read_excel(uploaded_file)
            st.success(f"✅ 成功加载 {len(df)} 条评论")

            # 提取预评分维度
            fixed_dims = ["设施", "卫生", "环境", "服务"]
            manual_scores = {}
            missing_cols = [col for col in fixed_dims if col not in df.columns]

            if missing_cols:
                st.warning(f"⚠️ 未找到评分列：{missing_cols}，将尝试从文本提取。")
            else:
                for dim in fixed_dims:
                    scores = pd.to_numeric(df[dim], errors='coerce').dropna()
                    if len(scores) > 0 and scores.between(1, 5).all():
                        manual_scores[dim] = round(scores.mean(), 2)
                    else:
                        st.warning(f"⚠️ {dim} 列数据无效，跳过。")

            # 从评论提取其他维度
            comment_col = '评论内容' if '评论内容' in df.columns else None
            if not comment_col:
                st.error("❌ 未找到“评论内容”列。")
            else:
                extracted_scores = extract_tags_with_scores(df[comment_col])
                # 避免重复
                extracted_scores = {k: v for k, v in extracted_scores.items() if k not in manual_scores}

            # 合并所有评分
            all_scores = {**manual_scores, **extracted_scores}
            if not all_scores:
                st.warning("⚠️ 未获取到任何评分。")
            else:
                all_scores_series = pd.Series(all_scores).sort_values(ascending=False)

                col1, col2 = st.columns(2)
                with col1:
                    st.subheader("📊 高分维度（≥4.5）")
                    high_scores = {k: v for k, v in all_scores_series.items() if v >= 4.5}
                    if high_scores:
                        fig, ax = plt.subplots(figsize=(10, 5))
                        colors = ['green' if v >= 4.78 else 'orange' for v in high_scores.values()]
                        pd.Series(high_scores).plot(kind='bar', ax=ax, color=colors, alpha=0.8)
                        ax.set_ylim(4.5, 5.0)
                        ax.axhline(y=4.78, color='red', linestyle='--', linewidth=1)
                        ax.text(0.02, 4.8, '优秀线 4.78', color='red', fontsize=10)
                        plt.xticks(rotation=45, ha='right')
                        plt.tight_layout()
                        st.pyplot(fig)
                    else:
                        st.info("当前无 ≥4.5 的维度")

                with col2:
                    st.subheader("📋 评分详情")
                    for dim, score in all_scores_series.items():
                        emoji = "🟢" if score >= 4.78 else "🟡"
                        source = "（手动）" if dim in manual_scores else "（文本）"
                        st.markdown(f"{emoji} **{dim}**: {score:.2f} {source}")

                # 优化建议
                st.subheader("💡 优化建议")
                low_scores = all_scores_series[all_scores_series < 4.78]
                if len(low_scores) == 0:
                    st.success("🎉 所有维度均 ≥ 4.78，表现优秀！")
                else:
                    for dim, score in low_scores.items():
                        default_sug = SUGGESTIONS.get(dim, "请补充优化建议。")
                        st.text_area(f"{dim} ({score:.2f})", value=default_sug, height=80, key=f"sug_{dim}")

                # 下载数据
                excel_data = to_excel(df)
                b64 = base64.b64encode(excel_data).decode()
                href = f'<a href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{b64}" download="原始数据.xlsx">📥 下载原始数据</a>'
                st.markdown(href, unsafe_allow_html=True)

        except Exception as e:
            st.error(f"❌ 处理失败：{str(e)}")

# ============ 2. 智能评论回复 ============
elif page == "💬 智能评论回复":
    st.title("💬 智能评论回复生成器")
    if not api_key:
        st.warning("⚠️ 请在侧边栏输入通义千问API密钥以启用此功能")
    else:
        comment_input = st.text_area("输入客人评论", height=150)
        if st.button("生成回复"):
            if comment_input.strip():
                with st.spinner("生成中..."):
                    prompt = generate_prompt(comment_input, st.session_state.hotel_name, st.session_state.hotel_location)
                    reply = call_qwen_api(prompt, api_key)
                    st.success("✅ 生成成功")
                    st.markdown(f"> {reply}")
            else:
                st.warning("请输入评论内容")

# ==================== 尾部 ====================
st.sidebar.divider()
st.sidebar.caption("© 2025 酒店智能运营系统")
