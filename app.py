# -*- coding: utf-8 -*-
"""
🏨 酒店运营一体化系统
功能：携程/美团评分预测 + 评论维度分析 + 智能评论回复
"""

import streamlit as st
import pandas as pd
import numpy as np
import math
import re
import matplotlib.pyplot as plt
from collections import defaultdict
from io import BytesIO
import base64
import jieba
import time
import datetime
import os
import requests

# ==================== 页面配置 ====================
st.set_page_config(page_title="Hotel OTA", layout="wide")

# ==================== 初始化 session_state ====================
if 'history' not in st.session_state:
    st.session_state.history = []

if 'hotel_name' not in st.session_state:
    st.session_state.hotel_name = "中油花园酒店"

if 'hotel_nickname' not in st.session_state:
    st.session_state.hotel_nickname = "小油"  # 默认昵称

if 'hotel_location' not in st.session_state:
    st.session_state.hotel_location = "该城市某处"

# ==================== 工具函数：Excel 导出 ====================
def to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='原始数据')
    return output.getvalue()

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
    '网络': ['Wi-Fi', '网络', '信号', '上网', '网速', 'wifi', '无线']
}

POSITIVE_WORDS = {'好', '棒', '赞', '满意', '不错', '推荐', '惊喜', '舒服', '完美', '贴心',
                  '干净', '方便', '快捷', '温馨', '柔软', '丰富', '齐全', '优质', '热情'}
NEGATIVE_WORDS = {'差', '糟', '烂', '坑', '差劲', '失望', '糟糕', '难用', '吵', '脏',
                  '贵', '偏', '慢', '不值', '问题', '敷衍', '拖延', '恶劣'}

def preprocess(text):
    """文本预处理：去除非中文/英文字符，分词"""
    text = re.sub(r'[^\u4e00-\u9fa5a-zA-Z]', '', str(text).lower())
    words = jieba.lcut(text)
    return [w for w in words if len(w) >= 2]

def get_sentiment_score(text):
    """基于关键词的情感分析"""
    words = preprocess(text)
    pos_count = sum(1 for w in words if w in POSITIVE_WORDS)
    neg_count = sum(1 for w in words if w in NEGATIVE_WORDS)
    total = pos_count + neg_count
    if total == 0:
        return 3.8  # 默认中性分
    if pos_count > neg_count:
        return min(5.0, 4.5 + 0.5 * (pos_count / total))
    elif neg_count > pos_count:
        return max(1.0, 2.5 - 0.5 * (neg_count / total))
    else:
        return 3.8

def extract_tags_with_scores(comments):
    """从评论中提取标签并计算情感得分"""
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

# ==================== 新增：提取评论维度与情感 ====================
def extract_aspects_and_sentiment(text):
    """
    从评论中提取涉及的维度（aspects）和整体情感倾向
    返回：dict(aspects=list, sentiment=str, has_complaint=bool, has_praise=bool, has_facility_issue=bool, has_noise=bool)
    """
    text_lower = str(text).lower()
    aspects = []
    has_complaint = False
    has_praise = False
    has_facility_issue = False
    has_noise = False

    for aspect, keywords in TAG_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            aspects.append(aspect)

    pos_count = sum(1 for word in POSITIVE_WORDS if word in text_lower)
    neg_count = sum(1 for word in NEGATIVE_WORDS if word in text_lower)

    if neg_count > pos_count:
        sentiment = "负面"
        has_complaint = True
    elif pos_count > neg_count:
        sentiment = "正面"
        has_praise = True
    else:
        sentiment = "中性"

    if any(kw in text_lower for kw in ['旧', '坏', '损坏', '故障', '设施陈旧', '设备老化']):
        has_facility_issue = True
    if any(kw in text_lower for kw in ['吵', '噪音', '隔音', '安静']):
        has_noise = True

    return {
        'aspects': aspects,
        'sentiment': sentiment,
        'has_complaint': has_complaint,
        'has_praise': has_praise,
        'has_facility_issue': has_facility_issue,
        'has_noise': has_noise
    }

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
    '网络': '升级Wi-Fi带宽，确保全区域稳定覆盖，设置一键连接页面。',
    '设施': '定期检修设备运行状态，补充人性化设施如USB充电口、小冰箱，增设无障碍通道。',
    '卫生': '加强清洁流程监督，使用可视化清洁标准，重点消毒高频接触区域。',
    '环境': '优化公共区域绿植布置，统一装修风格提升质感，营造主题化空间氛围。',
    '服务': '加强员工服务礼仪培训，建立快速响应机制，推行个性化主动服务。'
}

# ==================== 智能评论回复相关函数 ====================
def extract_aspects_and_sentiment(review: str):
    """模拟情感与方面提取（实际项目中应替换为真实NLP模型）"""
    aspects = []
    lower_review = review.lower()

    # 简单关键词匹配（仅作演示）
    if '交通' in lower_review or '位置' in lower_review or '地铁' in lower_review:
        aspects.append('交通')
    if '服务' in lower_review or '前台' in lower_review or '热情' in lower_review:
        aspects.append('服务')
    if '干净' in lower_review or '卫生' in lower_review or '整洁' in lower_review:
        aspects.append('卫生')
    if '早餐' in lower_review or '餐饮' in lower_review:
        aspects.append('早餐')
    if '划算' in lower_review or '价格' in lower_review or '性价比' in lower_review:
        aspects.append('性价比')
    if '安静' in lower_review or '环境' in lower_review or '风景' in lower_review:
        aspects.append('环境')
    if '设施' in lower_review or '设备' in lower_review or '老旧' in lower_review or '损坏' in lower_review:
        aspects.append('设施')

    # 情感判断
    positive_words = ['好', '棒', '赞', '满意', '推荐', '温馨', '舒服', '愉快']
    negative_words = ['差', '糟', '脏', '吵', '坏', '失望', '问题', '难用', '破损']

    pos_count = sum(1 for w in positive_words if w in lower_review)
    neg_count = sum(1 for w in negative_words if w in lower_review)

    sentiment = "正面" if pos_count > neg_count else "负面" if neg_count > pos_count else "中性"

    has_praise = pos_count > 0
    has_complaint = neg_count > 0
    has_facility_issue = any(w in lower_review for w in ['老旧', '损坏', '坏了', '故障', '不工作'])
    has_noise = any(w in lower_review for w in ['吵', '噪音', '响', '闹'])

    return {
        'aspects': list(set(aspects)),
        'sentiment': sentiment,
        'has_praise': has_praise,
        'has_complaint': has_complaint,
        'has_facility_issue': has_facility_issue,
        'has_noise': has_noise
    }

def generate_prompt(review: str, guest_name: str, hotel_name: str, hotel_nickname: str,
                    review_source: str, hotel_location: str, response_style: str = None):
    """生成给大模型的提示词（增强版，支持地理位置 + 回复风格）"""
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
    tags = "".join(tag_map.get(aspect, "") for aspect in info['aspects'])
    if not tags or info['sentiment'] == "负面":
        tags = "【🏨舒适入住🏨】"

    sentiment_guidance = ""
    if info['sentiment'] == "正面":
        sentiment_guidance = "客人对本次入住体验表示满意，重点表扬了某些方面。请表达感谢，并强调我们始终致力于提供高品质服务。"
    elif info['sentiment'] == "负面":
        sentiment_guidance = "客人对本次入住存在不满，可能涉及服务、设施或环境问题。请首先诚恳道歉，说明已记录反馈并正在改进，展现酒店的责任感与改进决心。"
    else:
        sentiment_guidance = "客人评论较为中立，未明确表达强烈情感。请表达欢迎与感谢，传递酒店的温暖与专业形象。"

    additional_notes = []
    if info['has_complaint']:
        additional_notes.append("注意：评论中包含负面反馈，请避免过度赞美，优先体现关怀与改进态度。")
    if info['has_praise']:
        additional_notes.append("注意：评论中包含明确表扬，请具体回应并表达感谢。")
    if info['has_facility_issue']:
        additional_notes.append("提及设施陈旧或损坏，请回应‘已反馈工程部评估升级’或类似表述。")
    if info['has_noise']:
        additional_notes.append("提及噪音问题，请承诺‘加强隔音管理’或‘优化客房分配策略’。")

    # 默认风格
    style_instruction = "使用正式、专业、温暖的语气，适合酒店官方形象。"
    if response_style:
        style_map = {
            "正式": "使用正式、庄重、专业的语气，体现酒店权威与规范。",
            "亲切": "使用温馨、口语化、像朋友一样的语气，让客人感到被关怀。",
            "幽默": "在不失礼的前提下，加入适度轻松幽默的表达，让人会心一笑。",
            "诗意": "用略带文艺、优美抒情的语言风格，营造浪漫氛围。",
            "简洁": "语言精炼直接，重点突出，避免冗余表达。"
        }
        style_instruction = style_map.get(response_style.strip(), style_instruction)

    prompt = f"""
    【角色设定】
    你是 {hotel_name} 的官方客服代表，昵称为“{hotel_nickname}”。你正在回复一位客人在 {review_source} 平台发布的评论。

    【酒店地理位置】
    {hotel_location}。请根据此信息灵活回应，如：
    - 若位置优越：可表达“感谢您认可我们优越的地理位置”
    - 若位置偏僻：可说明“虽地处安静区域，我们将持续优化交通指引”
    - 若近地铁/景区：可强调“便捷的交通/步行即可抵达景点”

    【任务要求】
    请撰写一条得体、有温度的中文回复，用于公开发布。必须满足以下所有规则：

    1. 开头必须包含以下标签：
       {tags}

    2. 称呼方式（二选一）：
       - 若评论含表扬：使用“亲爱的{guest_name}”；
       - 否则：使用“尊敬的宾客”。

    3. 回复语气必须符合以下情感导向：
       {sentiment_guidance}

    4. 风格要求：
       {style_instruction}

    5. 内容结构建议：
       - 正面评论：感谢 → 具体回应表扬点 → 结合地理位置说明优势 → 表达持续努力的决心 → 邀请再次光临
       - 负面评论：致歉 → 承认问题 → 说明改进措施 → 可提及位置优势弥补短板 → 邀请再次体验
       - 中性评论：感谢 → 简要回应内容 → 提及位置便利性 → 表达欢迎之意

    6. 字数严格控制在 150–250 个汉字之间（不含标签）。
    7. 禁止使用诗句、网络用语、过度夸张词汇（如“极其”“完美”）。
    8. 结尾必须包含类似“期待您再次光临，祝您生活愉快！”的表达。
    9. 不提及 API、模型、技术细节或内部流程。

    【附加提示】
    {' '.join(additional_notes) if additional_notes else '无特殊注意事项。'}

    【客人原始评论】
    {review}

    请直接输出最终回复内容，不要包含“回复：”等前缀。
    """
    return prompt

def call_qwen_api(prompt: str, api_key: str) -> str:
    """调用通义千问API"""
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
            "max_tokens": 300,
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

def call_qwen_api_multi(prompts: list, api_key: str) -> list:
    """并发调用API生成多条回复"""
    with concurrent.futures.ThreadPoolExecutor() as executor:
        results = list(executor.map(lambda p: call_qwen_api(p, api_key), prompts))
    return results

def truncate_to_word_count(text: str, min_words=150, max_words=250) -> str:
    """按汉字字符数截断文本（改为150–250）"""
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
        return truncated


# ==================== 侧边栏导航 ====================
st.sidebar.title("🏨 酒店OTA")
page = st.sidebar.radio("选择功能", [
    "📊 携程评分提升计算器",
    "📊 美团评分提升计算器",
    "📈 评论维度分析",
    "💬 智能评论回复"
])

# 全局配置
st.sidebar.divider()
st.sidebar.subheader("⚙️ 酒店配置")
hotel_name = st.sidebar.text_input("酒店名称", st.session_state.hotel_name)

# ✅ 新增：地理位置输入
hotel_location = st.sidebar.text_input(
    "酒店地理位置描述",
    st.session_state.get('hotel_location', ''),
    help="例如：市中心繁华地段、近地铁2号线湖滨站、西湖景区旁安静区域等"
)

if st.sidebar.button("💾 保存配置"):
    st.session_state.hotel_name = hotel_name.strip() or "未命名酒店"
    if hotel_location.strip():
        st.session_state.hotel_location = hotel_location.strip()
    else:
        st.session_state.hotel_location = "该城市某处"
    st.sidebar.success("✅ 配置已保存")

# ==================== 主页面逻辑 ====================

# ============ 1. 携程评分计算器 ============
if page == "📊 携程评分提升计算器":
    st.title("📊 携程评分提升计算器")

    col1, col2, col3 = st.columns(3)
    with col1:
        current_score = st.number_input("当前评分", 0.0, 5.0, 4.52, 0.01)
    with col2:
        total_reviews = st.number_input("当前总评价数", 0, 10000, 500, 1)
    with col3:
        target_score = st.number_input("目标评分", 0.0, 5.0, 4.80, 0.01)

    def calculate_simple():
        if current_score >= target_score:
            return 0
        numerator = (target_score - current_score) * total_reviews
        denominator = 5.0 - target_score
        if denominator <= 0:
            raise ValueError("目标评分必须小于5.0")
        required = math.ceil(numerator / denominator)
        return max(0, required)

    try:
        req = calculate_simple()
        if req == 0:
            st.info(f"🎉 当前评分 **{current_score:.2f}** 已达到或超过目标 **{target_score:.2f}**")
        else:
            st.warning(f"📈 需要至少 **{req}** 条 5 星好评才能达到 **{target_score:.2f}** 分")
    except Exception as e:
        st.error(f"❌ 计算错误：{str(e)}")

# ============ 2. 美团评分计算器 ============
elif page == "📊 美团评分提升计算器":
    st.title("美团酒店评分提升计算器（简化版）")

    col1, col2, col3 = st.columns(3)
    with col1:
        current_score = st.number_input("当前评分", 0.0, 5.0, 4.52, 0.01)
    with col2:
        total_reviews = st.number_input("当前总评价数", 0, 10000, 800, 1)
    with col3:
        target_score = st.number_input("目标评分", 0.0, 5.0, 4.80, 0.01)

    def calculate_simple():
        if current_score >= target_score:
            return 0
        numerator = (target_score - current_score) * total_reviews
        denominator = 5.0 - target_score
        if denominator <= 0:
            raise ValueError("目标评分必须小于 5.0")
        required = math.ceil(numerator / denominator)
        return max(0, required)

    try:
        req = calculate_simple()
        if req == 0:
            st.info(f"🎉 当前评分 **{current_score:.2f}** 已达到或超过目标 **{target_score:.2f}**")
        else:
            st.warning(f"📈 需要至少 **{req}** 条 5 星好评才能达到 **{target_score:.2f}** 分")
    except Exception as e:
        st.error(f"❌ 计算错误：{str(e)}")

# ============ 3. 评论维度分析 ============
if page == "📈 评论维度分析":
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
                # 提取评论内容中的标签评分
                new_scores = extract_tags_with_scores(df[comment_col])

                # 读取Excel中已有的维度评分
                dimension_cols = ['设施', '卫生', '环境', '服务']  # 根据实际情况调整维度列名
                existing_scores = df[dimension_cols].mean().to_dict()

                # 合并新旧评分
                all_scores = {**new_scores, **existing_scores}

                if len(all_scores) == 0:
                    st.warning("⚠️ 未提取到任何有效标签评分")
                else:
                    all_scores = pd.Series(all_scores).sort_values(ascending=False)

                    # 调整列的比例，使柱状图占据更多空间
                    col1, _ = st.columns([3, 1])
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
                    
                        # 替换为表格形式展示各维度评分
                        st.markdown("### 🔽 各维度评分")
                        if len(all_scores) > 0:
                            table_data = []
                            for dimension, score in all_scores.items():
                                table_data.append([dimension, f"{score:.2f}"])
                            
                            df_table = pd.DataFrame(table_data, columns=["维度", "评分"])
                            st.table(df_table)
                        else:
                            st.caption("暂无评分数据")
                        st.subheader("💡 优化建议（可修改）")
                        needs_improvement = all_scores[all_scores < 4.78]
                        if len(needs_improvement) == 0:
                            st.success("🎉 所有维度均 ≥ 4.78，表现优秀！")
                        else:
                            for dim, score in needs_improvement.items():
                                default_suggestion = SUGGESTIONS.get(dim, "请补充优化建议。")
                                st.markdown(f"### 📌 {dim} ({score:.2f})")
                                st.text_area("建议：", value=default_suggestion, height=100, key=f"sug_{dim}")

                        excel_data = to_excel(df)
                        b64 = base64.b64encode(excel_data).decode()
                        href = f'<a href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{b64}" download="原始评论数据.xlsx">📥 下载原始数据</a>'
                        st.markdown(href, unsafe_allow_html=True)

        except Exception as e:
            st.error(f"❌ 数据处理失败：{str(e)}")
# ============ 4. 智能评论回复（增强版） ============
elif page == "💬 智能评论回复":
    st.title("智能评论回复生成器")

    try:
        QWEN_API_KEY = st.secrets["QWEN_API_KEY"]
    except KeyError:
        QWEN_API_KEY = os.getenv("QWEN_API_KEY")

    if not QWEN_API_KEY or not QWEN_API_KEY.startswith("sk-"):
        st.warning("⚠️ 请设置有效的 Qwen API Key")
        st.markdown("""
        **设置方法：**
        1. 在 Streamlit Cloud 的应用设置中打开 **Secrets**；
        2. 添加：`QWEN_API_KEY = "sk-你的密钥"`；
        3. 重新部署。
        """)
        st.stop()

    col1, col2 = st.columns([3, 1])
    with col1:
        review_input = st.text_area("粘贴客人评论", height=180, placeholder="请在此输入或粘贴客人在携程/美团等平台的评论...")
    with col2:
        guest_name = st.text_input("客人姓名", "尊敬的宾客")
        review_source = st.selectbox("平台来源", ["携程", "美团", "飞猪", "去哪儿", "抖音"])
        response_style = st.selectbox(
            "回复风格（可选）",
            options=["不指定", "正式", "亲切", "幽默", "诗意", "简洁"],
            index=0,
            help="选择一种风格，让回复更具个性。不选则使用默认专业风格。"
        )

    if st.button("✨ 生成三条回复", type="primary"):
        if not review_input.strip():
            st.warning("请输入评论内容！")
        else:
            with st.spinner("正在生成三条不同风格的回复..."):

                # 定义三种风格策略
                style_options = ["正式", "亲切", "简洁"]

                # 如果用户指定了风格，优先使用它作为主风格，其余为备选
                if response_style and response_style != "不指定":
                    style_options = [response_style, "正式", "亲切"]

                # 生成三个不同的 prompt
                prompts = [
                    generate_prompt(
                        review_input, guest_name,
                        st.session_state.hotel_name,
                        st.session_state.hotel_nickname,
                        review_source,
                        st.session_state.get('hotel_location', '该城市某处'),
                        style
                    )
                    for style in style_options
                ]

                # 并行调用 API
                raw_replies = call_qwen_api_multi(prompts, QWEN_API_KEY)

                # 处理每条回复
                replies = []
                word_counts = []
                for reply in raw_replies:
                    if not reply.startswith("❌") and not reply.startswith("🚨"):
                        cleaned = truncate_to_word_count(reply)
                    else:
                        cleaned = reply
                    replies.append(cleaned)
                    word_count = len([c for c in cleaned if c.isalnum() or c in '，。！？；：""''（）【】《》、'])
                    word_counts.append(word_count)

            # 显示三条回复供选择
            st.markdown("### 🎯 三条候选回复")

            for i, (reply, wc) in enumerate(zip(replies, word_counts)):
                with st.expander(f"回复 {i+1} | 字数：{wc}"):
                    st.markdown(f"""
                    <div style="background-color: #000000; color: #ffffff; padding: 12px; border-radius: 6px; font-size: 15px; line-height: 1.6;">
                    {reply}
                    </div>
                    """, unsafe_allow_html=True)

                    # 复制按钮
                    st.markdown(f"""
                    <script src="https://cdn.jsdelivr.net/npm/clipboard@2/dist/clipboard.min.js"></script>
                    <button id="copy-btn-{i}" style="margin-top: 8px; padding: 6px 12px; background: #1f77b4; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 14px;">
                        📋 复制此回复
                    </button>
                    <script>
                    const btn{i} = document.getElementById('copy-btn-{i}');
                    const text{i} = `{reply.replace("`", "\\`")}`;
                    const clipboard{i} = new ClipboardJS('#copy-btn-{i}', {{ text: () => text{i} }});
                    clipboard{i}.on('success', function(e) {{
                        btn{i}.innerText = '✅ 已复制！';
                        setTimeout(() => {{ btn{i}.innerText = '📋 复制此回复'; }}, 2000);
                    }});
                    </script>
                    """, unsafe_allow_html=True)

                    # 保存按钮
                    if st.button(f"💾 保存第{i+1}条", key=f"save_{i}"):
                        st.session_state.history.append({
                            "time": time.strftime("%H:%M"),
                            "hotel": st.session_state.hotel_name,
                            "name": guest_name,
                            "review": review_input[:50] + "...",
                            "reply": reply,
                            "word_count": wc
                        })
                        st.success(f"第{i+1}条回复已保存至历史记录")

    # 历史记录
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
                    st.rerun()
# ==================== 尾部信息 ====================
st.sidebar.divider()
st.sidebar.caption(f"@ 2025 {st.session_state.hotel_nickname} 酒店运营工具")











