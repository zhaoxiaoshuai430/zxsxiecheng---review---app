# -*- coding: utf-8 -*-
"""
🏨 酒店运营一体化系统
功能：携程/美团评分计算 + 评论维度分析（文本挖掘）+ 智能评论回复
"""

import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from io import BytesIO
import base64
import requests
import time
import re
import os
from datetime import datetime
import jieba
from collections import defaultdict
import squarify
import matplotlib

# 设置中文字体支持
matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'DejaVu Sans', 'Microsoft YaHei']
matplotlib.rcParams['axes.unicode_minus'] = False

# ==================== 页面配置 ====================
st.set_page_config(page_title="Hotel OTA", layout="centered")

# ==================== 初始化 session_state ====================
if 'history' not in st.session_state:
    st.session_state.history = []

if 'hotel_name' not in st.session_state:
    st.session_state.hotel_name = "星辰花园酒店"
if 'hotel_nickname' not in st.session_state:
    st.session_state.hotel_nickname = "小油"

# ==================== 工具函数：Excel 导出 ====================
def to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='原始数据')
    return output.getvalue()

# ==================== 工具函数：加权评分计算 ====================
def calculate_time_and_rank_weighted_score(df, score_col, date_col="入住时间"):
    df = df.copy()
    df[score_col] = pd.to_numeric(df[score_col], errors='coerce')
    df = df.dropna(subset=[score_col, date_col])
    df = df[(df[score_col] >= 1) & (df[score_col] <= 5)]

    if len(df) == 0:
        return 0.0

    try:
        df[date_col] = pd.to_datetime(df[date_col])
    except Exception as e:
        st.error(f"❌ 日期格式错误：{e}")
        return 0.0

    lambda_decay = 0.05
    latest_date = df[date_col].max()
    df['天数差'] = (latest_date - df[date_col]).dt.days
    df['时间权重'] = np.exp(-lambda_decay * df['天数差'])

    weight_map = {5: 1, 4: 2, 3: 3, 2: 4, 1: 5}
    df['评分权重'] = df[score_col].map(weight_map)
    df['总权重'] = df['时间权重'] * df['评分权重']
    df['加权分数'] = df[score_col] * df['总权重']

    total_weighted_score = df['加权分数'].sum()
    total_weight = df['总权重'].sum()

    if total_weight == 0:
        return 0.0

    weighted_avg = total_weighted_score / total_weight
    final_score = max(weighted_avg - 0.20, 1.0)
    return round(final_score, 2)

# ==================== 工具函数：情感分析与标签提取 ====================
TAG_KEYWORDS = {
    '位置': ['位置', '地段', '周边', '附近', '离', '靠近', '市中心', '地铁', '公交'],
    '交通': ['交通', '打车', '停车', '驾车', '机场', '车站', '接驳'],
    '早餐': ['早餐', '早饭', '餐饮', 'buffet', '餐食', '自助餐'],
    '安静': ['安静', '噪音', '吵', '吵闹', '隔音', '清静', '安静房'],
    '床舒适': ['床', '床垫', '睡感', '舒服', '舒不舒服', '软硬', '枕头'],
    '房间大小': ['房间小', '房间大', '空间', '拥挤', '宽敞', '面积', '局促'],
    '视野': ['视野', '景观', '江景', '海景', '窗景', '朝向', '夜景', 'view'],
    '性价比': ['性价比', '价格', '划算', '贵', '便宜', '值', '物超所值'],
    '前台': ['前台', '接待', 'check in', '入住办理', '退房', '接待员'],
    '网络': ['Wi-Fi', '网络', '信号', '上网', '网速', 'wifi', '无线']
}

POSITIVE_WORDS = {'好', '棒', '赞', '满意', '不错', '推荐', '惊喜', '舒服', '完美', '贴心',
                  '干净', '方便', '快捷', '温馨', '柔软', '丰富', '齐全', '优质', '热情'}
NEGATIVE_WORDS = {'差', '糟', '烂', '坑', '差劲', '失望', '糟糕', '难用', '吵', '脏',
                  '贵', '偏', '慢', '不值', '问题', '敷衍', '拖延', '恶劣'}

def preprocess(text):
    text = re.sub(r'[^\u4e00-\u9fa5a-zA-Z]', '', str(text).lower())
    words = jieba.lcut(text)
    return [w for w in words if len(w) >= 2]

def get_sentiment_score(text):
    words = preprocess(text)
    pos_count = sum(1 for w in words if w in POSITIVE_WORDS)
    neg_count = sum(1 for w in words if w in NEGATIVE_WORDS)
    total = pos_count + neg_count
    if total == 0:
        return 3.8
    if pos_count > neg_count:
        return min(5.0, 4.5 + 0.5 * (pos_count / total))
    elif neg_count > pos_count:
        return max(1.0, 2.5 - 0.5 * (neg_count / total))
    else:
        return 3.8

def extract_tags_with_scores(comments):
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

# ==================== 工具函数：智能评论回复 ====================
def extract_aspects_and_sentiment(review: str) -> dict:
    aspects = {
        '交通': ['地铁', '交通', '停车', '位置', '方便', '直达', '高铁', '火车站'],
        '服务': ['服务', '前台', '热情', '周到', '专业', '响应', '处理'],
        '卫生': ['干净', '卫生', '整洁', '无异味', '一尘不染', '脏', '灰尘'],
        '早餐': ['早餐', '可口', '丰富', '美味', '种类', '奶酥包', '现烤'],
        '性价比': ['性价比', '划算', '便宜', '物超所值', '贵'],
        '环境': ['环境', '安静', '舒适', '优美', '风景', '隔音', '吵', '噪音'],
        '设施': ['设施', '陈旧', '老化', '智能', '空调', '电视', '床品', '地毯', '壁纸']
    }
    found = []
    for k, keywords in aspects.items():
        if any(w in review.lower() for w in [w.lower() for w in keywords]):
            found.append(k)

    pos_words = ['好', '棒', '满意', '喜欢', '推荐', '舒服', '专业', '周到', '可口', '方便', '安静', '整洁']
    neg_words = ['差', '糟', '失望', '脏', '慢', '贵', '问题', '吵', '损坏', '遗憾', '陈旧', '噪音', '不隔音']

    pos_score = sum(review.lower().count(w) for w in [w.lower() for w in pos_words])
    neg_score = sum(review.lower().count(w) for w in [w.lower() for w in neg_words])

    sentiment = "正面" if pos_score > neg_score else "负面" if neg_score > pos_score else "中性"

    return {
        "aspects": list(set(found)),
        "sentiment": sentiment,
        "has_complaint": neg_score > 0,
        "has_praise": pos_score > 0,
        "has_facility_issue": any(w in review for w in ['陈旧', '老化', '损坏', '故障', '旧']),
        "has_noise": any(w in review for w in ['吵', '噪音', '不隔音', '安静']),
        "has_service_staff": bool(re.search(r'[a-zA-Z\u4e00-\u9fff]{2,4}', review))
    }

def generate_prompt(review: str, guest_name: str, hotel_name, hotel_nickname, review_source):
    info = extract_aspects_and_sentiment(review)

    tag_map = {
        '交通': '【❤️交通便利❤️】',
        '服务': '【❤️服务周到❤️】',
        '卫生': '【✅干净整洁✅】',
        '早餐': '【🍳早餐可口🍳】',
        '性价比': '【💰性价比高💰】',
        '环境': '【🌿安静舒适🌿】',
        '设施': '【🔧设施完善🔧】'
    }
    tags = "".join(tag_map[aspect] for aspect in info['aspects'] if aspect in tag_map and info['sentiment'] != "负面")
    if not tags:
        tags = "【🏨舒适入住🏨】"

    prompt = f"""
    你是 {hotel_name} 的客服助手“{hotel_nickname}”，正在回复客人在 {review_source} 上的评论。
    请用规范、专业、真诚的语气撰写回复。

    要求：
    1. 开头使用标签：{tags}
    2. 称呼：“尊敬的宾客”或“亲爱的{guest_name}”
    3. 好评：感谢 + 认可
    4. 差评：致歉 + 整改措施
    5. 严格控制在100-200个汉字之间
    6. 不使用诗句、哲理、网络用语
    7. 结尾表达期待再次光临

    【客人评论】：
    {review}
    """
    return prompt

def call_qwen_api(prompt: str) -> str:
    api_key = os.getenv("QWEN_API_KEY")
    if not api_key:
        return "❌ 未设置 QWEN_API_KEY 环境变量，请在 Streamlit Cloud 的 Secrets 中配置。"

    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    payload = {
        "model": "qwen-max",
        "input": {
            "messages": [{"role": "user", "content": prompt}]
        },
        "parameters": {
            "result_format": "text",
            "max_tokens": 200,
            "temperature": 0.6,
            "top_p": 0.85
        }
    }
    try:
        response = requests.post("https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation",
                                 headers=headers, json=payload, timeout=30)
        if response.status_code == 200:
            result = response.json()
            return result['output']['text'].strip()
        else:
            return f"❌ API 错误 [{response.status_code}]：{response.text}"
    except Exception as e:
        return f"🚨 请求失败：{str(e)}"

def truncate_to_word_count(text: str, min_words=100, max_words=200) -> str:
    words = [c for c in text if c.isalnum() or c in '，。！？；：""''（）【】《》、']
    content = ''.join(words)
    if len(content) <= max_words:
        return content
    else:
        truncated = content[:max_words]
        for punct in ['。', '！', '？']:
            if punct in truncated:
                truncated = truncated[:truncated.rfind(punct) + 1]
                break
        if len(truncated) < min_words:
            truncated = content[:max_words]
        return truncated[:max_words]

# ==================== 优化建议库 ====================
SUGGESTIONS = {
    '总评分': '整体体验需提升，建议从服务和设施入手，加强客户反馈闭环管理。',
    '设施评分': '检查老旧设备，制定更新计划，增加智能化设施如智能门锁、语音助手。',
    '服务评分': '加强员工服务意识培训，建立快速响应机制处理差评。',
    '卫生评分': '加强清洁流程监督，引入第三方质检或公示消毒记录增强信任。',
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

# ==================== 侧边栏导航 ====================
st.sidebar.title("🏨 酒店OTA")
page = st.sidebar.radio("选择功能", [
    "📊 携程评分计算器",
    "📊 美团评分计算器",
    "📈 评论维度分析",
    "💬 智能评论回复"
])

# 全局配置
st.sidebar.divider()
st.sidebar.subheader("⚙️ 酒店配置")
hotel_name = st.sidebar.text_input("酒店名称", st.session_state.hotel_name)
hotel_nickname = st.sidebar.text_input("助手昵称", st.session_state.hotel_nickname)
if st.sidebar.button("💾 保存配置"):
    st.session_state.hotel_name = hotel_name.strip() or "未命名酒店"
    st.session_state.hotel_nickname = hotel_nickname.strip() or "助手"
    st.sidebar.success("✅ 配置已保存")

# ==================== 主页面逻辑 ====================

# ============ 1. 携程评分计算器 ============
if page == "📊 携程评分计算器":
    st.title("携程酒店评分提升计算器")

    col1, col2, col3 = st.columns(3)
    with col1:
        weighted_current_score = st.number_input("当前加权综合评分", 0.0, 5.0, 4.52, 0.01)
        score_3_years_ago = st.number_input("三年前评分", 0.0, 5.0, 4.70, 0.01)
    with col2:
        reviews_last_3_years = st.number_input("近三年评价数", 0, 10000, 500, 1)
        reviews_before_3_years = st.number_input("三年前评价数", 0, 10000, 300, 1)
    with col3:
        target_score = st.number_input("目标评分", 0.0, 5.0, 4.80, 0.01)

    def calculate_xiecheng():
        effective_old = reviews_before_3_years / 10.0
        total_weight = reviews_last_3_years + effective_old
        inferred_recent_score = (
            (weighted_current_score * total_weight - score_3_years_ago * effective_old)
            / reviews_last_3_years
        )
        if weighted_current_score >= target_score:
            return 0, inferred_recent_score

        numerator = (target_score * total_weight - score_3_years_ago * effective_old) - inferred_recent_score * reviews_last_3_years
        denominator = 5.0 - target_score
        if denominator <= 0:
            raise ValueError("目标评分过高")
        required = math.ceil(numerator / denominator)
        return max(0, required), inferred_recent_score

    try:
        req, inferred = calculate_xiecheng()
        st.success(f"✅ 反推出近三年真实评分为：**{inferred:.3f} 分**")
        if req == 0:
            st.info(f"🎉 当前评分已达到目标 **{target_score:.2f}** 分")
        else:
            st.warning(f"📈 需要至少 **{req}** 条 5 星好评")
    except Exception as e:
        st.error(f"❌ 计算错误：{str(e)}")

# ============ 2. 美团评分计算器 ============
elif page == "📊 美团评分计算器":
    st.title("美团酒店评分提升计算器")

    col1, col2, col3 = st.columns(3)
    with col1:
        weighted_current_score = st.number_input("当前加权综合评分", 0.0, 5.0, 4.52, 0.01)
        score_1_year_ago = st.number_input("一年前评分", 0.0, 5.0, 4.60, 0.01)
    with col2:
        reviews_last_1_year = st.number_input("近一年评价数", 0, 10000, 300, 1)
        reviews_before_1_year = st.number_input("一年前评价数", 0, 10000, 500, 1)
    with col3:
        target_score = st.number_input("目标评分", 0.0, 5.0, 4.80, 0.01)

    def calculate_meituan():
        effective_old = reviews_before_1_year / 10.0
        total_weight = reviews_last_1_year + effective_old
        inferred_recent_score = (
            (weighted_current_score * total_weight - score_1_year_ago * effective_old)
            / reviews_last_1_year
        )
        if weighted_current_score >= target_score:
            return 0, inferred_recent_score

        numerator = (target_score * total_weight - score_1_year_ago * effective_old) - inferred_recent_score * reviews_last_1_year
        denominator = 5.0 - target_score
        if denominator <= 0:
            raise ValueError("目标评分过高")
        required = math.ceil(numerator / denominator)
        return max(0, required), inferred_recent_score

    try:
        req, inferred = calculate_meituan()
        st.success(f"✅ 反推出近一年真实评分为：**{inferred:.3f} 分**")
        if req == 0:
            st.info(f"🎉 当前评分已达标")
        else:
            st.warning(f"📈 需要至少 **{req}** 条 5 星好评")
    except Exception as e:
        st.error(f"❌ 计算错误：{str(e)}")

# ============ 3. 评论维度分析（新） ============
elif page == "📈 评论维度分析":
    st.title("📈 评论维度分析（基于文本挖掘）")

    st.markdown("上传包含 **评论内容** 列的 Excel 文件，系统将自动提取标签并分析情感。")

    with st.expander("📄 示例格式"):
        st.write(pd.DataFrame({
            '评论内容': ["位置很好，靠近地铁，但房间有点小。", "早餐丰富，服务热情，就是有点吵。"]
        }))

    uploaded_file = st.file_uploader("上传评论数据 (.xlsx)", type=["xlsx"])

    if uploaded_file:
        try:
            df = pd.read_excel(uploaded_file)
            st.success(f"✅ 成功加载 {len(df)} 条评论数据")

            with st.expander("📄 数据预览"):
                st.dataframe(df.head())

            # 查找评论列
            comment_col = None
            if '评论内容' in df.columns:
                comment_col = '评论内容'
            else:
                potential = [col for col in df.columns if '评论' in col or '评价' in col or 'content' in col]
                if potential:
                    comment_col = potential[0]

            if not comment_col:
                st.error("❌ 未找到评论列，请确保包含“评论”或“评价”关键词的列。")
            else:
                # 提取标签评分
                new_scores = extract_tags_with_scores(df[comment_col])

                if len(new_scores) == 0:
                    st.warning("⚠️ 未提取到任何有效标签评分")
                else:
                    all_scores = pd.Series(new_scores).sort_values(ascending=False)

                    # 可视化
                    col1, col2 = st.columns(2)

                    with col1:
                        st.subheader("📊 柱状图：各维度评分")
                        filtered_scores = {k: v for k, v in all_scores.items() if 4.5 <= v <= 5.0}
                        fig1, ax1 = plt.subplots(figsize=(10, 6))
                        colors = ['green' if v >= 4.78 else 'red' for v in filtered_scores.values()]
                        pd.Series(filtered_scores).plot(kind='bar', ax=ax1, color=colors, alpha=0.8)
                        ax1.set_ylabel("评分（满分5.0）")
                        ax1.set_ylim(4.5, 5.0)
                        ax1.axhline(y=4.78, color='orange', linestyle='--', linewidth=1)
                        ax1.text(0.02, 4.8, '优秀线 4.78', transform=ax1.transData, fontsize=10, color='orange')
                        plt.xticks(rotation=45, ha='right')
                        plt.tight_layout()
                        st.pyplot(fig1)

                    with col2:
                        st.subheader("📈 树状图（Treemap）")
                        fig2, ax2 = plt.subplots(figsize=(10, 6))
                        sizes = all_scores.values
                        colors = ['lightgreen' if v >= 4.78 else 'salmon' for v in all_scores]
                        labels = [f'{k}\n{v:.2f}' for k, v in all_scores.items()]
                        squarify.plot(sizes=sizes, label=labels, color=colors, alpha=0.8, ax=ax2, text_kwargs={'fontsize': 8})
                        ax2.set_title("评分分布")
                        ax2.axis("off")
                        st.pyplot(fig2)

                    # 优化建议
                    st.subheader("💡 优化建议（可修改）")
                    needs_improvement = all_scores[all_scores < 4.78]
                    if len(needs_improvement) == 0:
                        st.success("🎉 所有维度均 ≥ 4.78，表现优秀！")
                    else:
                        for dim, score in needs_improvement.items():
                            default_suggestion = SUGGESTIONS.get(dim, "请补充优化建议。")
                            st.markdown(f"### 📌 {dim} ({score:.2f})")
                            st.text_area("建议：", value=default_suggestion, height=100, key=f"sug_{dim}")

                    # 导出原始数据
                    excel_data = to_excel(df)
                    b64 = base64.b64encode(excel_data).decode()
                    href = f'<a href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{b64}" download="原始评论数据.xlsx">📥 下载原始数据</a>'
                    st.markdown(href, unsafe_allow_html=True)

        except Exception as e:
            st.error(f"❌ 数据处理失败：{str(e)}")
            st.exception(e)

# ============ 4. 智能评论回复 ============
elif page == "💬 智能评论回复":
    st.title("💬 智能评论回复生成器")

    col1, col2 = st.columns([3, 1])
    with col1:
        review_input = st.text_area("粘贴客人评论", height=180, placeholder="请在此输入或粘贴客人在携程/美团等平台的评论...")
    with col2:
        guest_name = st.text_input("客人姓名", "尊敬的宾客")
        review_source = st.selectbox("平台来源", ["携程", "美团", "飞猪", "去哪儿", "抖音"])

    if st.button("✨ 生成回复", type="primary"):
        if not review_input.strip():
            st.warning("请输入评论内容！")
        else:
            with st.spinner("正在生成回复..."):
                prompt = generate_prompt(
                    review_input, guest_name,
                    st.session_state.hotel_name,
                    st.session_state.hotel_nickname,
                    review_source
                )
                raw_reply = call_qwen_api(prompt)
                reply = truncate_to_word_count(raw_reply) if not raw_reply.startswith("❌") else raw_reply
                word_count = len([c for c in reply if c.isalnum() or c in '，。！？；：""''（）【】《》、'])

            st.markdown(f"""
            <div style="background-color: #000000; color: #ffffff; padding: 12px; border-radius: 6px; font-size: 15px;">
            {reply}
            </div>
            <p style="color: #888; font-size: 14px; margin-top: 4px;">
            🔤 字数：{word_count} / 200（目标区间：100–200）
            </p>
            """, unsafe_allow_html=True)

            st.markdown("""
            <script src="https://cdn.jsdelivr.net/npm/clipboard@2/dist/clipboard.min.js"></script>
            <button id="copy-btn" style="margin-top: 10px; padding: 8px 16px; background: #1f77b4; color: white; border: none; border-radius: 4px; cursor: pointer;">
                📋 复制回复
            </button>
            <script>
            const btn = document.getElementById('copy-btn');
            const text = document.querySelector('div[style*="background-color: #000000"]').innerText;
            const clipboard = new ClipboardJS('#copy-btn', { text: () => text });
            clipboard.on('success', function(e) {
                btn.innerText = '✅ 已复制！';
                setTimeout(() => { btn.innerText = '📋 复制回复'; }, 2000);
            });
            </script>
            """, unsafe_allow_html=True)

            if st.button("💾 保存到历史"):
                st.session_state.history.append({
                    "time": time.strftime("%H:%M"),
                    "hotel": st.session_state.hotel_name,
                    "name": guest_name,
                    "review": review_input[:50] + "...",
                    "reply": reply,
                    "word_count": word_count
                })
                st.success("已保存至历史记录")

    if st.session_state.history:
        st.subheader("🕒 历史记录")
        for idx, h in enumerate(reversed(st.session_state.history)):
            with st.expander(f"【{h['time']}】{h['hotel']} | {h['name']} | {h['word_count']}字"):
                st.markdown(f"""
                <div style="background-color: #000000; color: #ffffff; padding: 12px; border-radius: 6px; font-size: 15px;">
                {h['reply']}
                </div>
                """, unsafe_allow_html=True)
                if st.button(f"🗑️ 删除记录 {idx}", key=f"del_{idx}"):
                    st.session_state.history.pop(-idx-1)
                    st.experimental_rerun()

# ============ API Key 提醒 ============
if page == "💬 智能评论回复" and not os.getenv("QWEN_API_KEY"):
    st.warning("⚠️ 请在 Streamlit Cloud 的 Secrets 中设置 `QWEN_API_KEY`")
