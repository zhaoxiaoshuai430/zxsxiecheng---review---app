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
import os  # 新增：用于读取环境变量
import requests  # 新增：用于调用 Qwen API

# ==================== 页面配置 ====================
st.set_page_config(page_title="Hotel OTA", layout="wide")

# ==================== 初始化 session_state ====================
if 'history' not in st.session_state:
    st.session_state.history = []

if 'hotel_name' not in st.session_state:
    st.session_state.hotel_name = "中油花园酒店"
if 'hotel_nickname' not in st.session_state:
    st.session_state.hotel_nickname = "小油"

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
    '前台': ['前台', '接待', 'check in', '入住办理', '退房', '接待员'],
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

# ==================== 智能评论回复相关函数 ====================
def generate_prompt(review: str, guest_name: str, hotel_name: str, hotel_nickname: str, review_source: str):
    """生成给大模型的提示词（优化版）"""
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
    # 只在正面或中性评价中展示标签
    tags = "".join(tag_map[aspect] for aspect in info['aspects'] if aspect in tag_map)
    if not tags or info['sentiment'] == "负面":
        tags = "【🏨舒适入住🏨】"

    # 构建更精确的情感导向说明
    sentiment_guidance = ""
    if info['sentiment'] == "正面":
        sentiment_guidance = "客人对本次入住体验表示满意，重点表扬了某些方面。请表达感谢，并强调我们始终致力于提供高品质服务。"
    elif info['sentiment'] == "负面":
        sentiment_guidance = "客人对本次入住存在不满，可能涉及服务、设施或环境问题。请首先诚恳道歉，说明已记录反馈并正在改进，展现酒店的责任感与改进决心。"
    else:  # 中性
        sentiment_guidance = "客人评论较为中立，未明确表达强烈情感。请表达欢迎与感谢，传递酒店的温暖与专业形象。"

    # 细节补充（用于增强回复针对性）
    additional_notes = []
    if info['has_complaint']:
        additional_notes.append("注意：评论中包含负面反馈，请避免过度赞美，优先体现关怀与改进态度。")
    if info['has_praise']:
        additional_notes.append("注意：评论中包含明确表扬，请具体回应并表达感谢。")
    if info['has_facility_issue']:
        additional_notes.append("提及设施陈旧或损坏，请回应‘已反馈工程部评估升级’或类似表述。")
    if info['has_noise']:
        additional_notes.append("提及噪音问题，请承诺‘加强隔音管理’或‘优化客房分配策略’。")

    prompt = f"""
    【角色设定】
    你是 {hotel_name} 的官方客服代表，昵称为“{hotel_nickname}”。你正在回复一位客人在 {review_source} 平台发布的评论。

    【任务要求】
    请撰写一条正式、得体、有温度的中文回复，用于公开发布。必须满足以下所有规则：

    1. 开头必须包含以下标签：
       {tags}

    2. 称呼方式（二选一）：
       - 若评论含表扬：使用“亲爱的{guest_name}”；
       - 否则：使用“尊敬的宾客”。

    3. 回复语气必须符合以下情感导向：
       {sentiment_guidance}

    4. 内容结构建议：
       - 正面评论：感谢 → 具体回应表扬点 → 表达持续努力的决心 → 邀请再次光临
       - 负面评论：致歉 → 承认问题 → 说明改进措施 → 邀请再次体验
       - 中性评论：感谢 → 简要回应内容 → 表达欢迎之意

    5. 字数严格控制在 100–200 个汉字之间（不含标签）。
    6. 禁止使用诗句、网络用语、过度夸张词汇（如“极其”“完美”）。
    7. 结尾必须包含类似“期待您再次光临，祝您生活愉快！”的表达。
    8. 不提及 API、模型、技术细节或内部流程。

    【附加提示】
    {' '.join(additional_notes) if additional_notes else '无特殊注意事项。'}

    【客人原始评论】
    {review}

    请直接输出最终回复内容，不要包含“回复：”等前缀。
    """
    return prompt

def call_qwen_api(prompt: str) -> str:
    """调用通义千问API"""
    headers = {
        'Authorization': f'Bearer {QWEN_API_KEY}',
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
        response = requests.post(QWEN_API_URL, headers=headers, json=payload, timeout=30)
        if response.status_code == 200:
            result = response.json()
            return result['output']['text'].strip()
        else:
            return f"❌ API 错误 [{response.status_code}]：{response.text}"
    except Exception as e:
        return f"🚨 请求失败：{str(e)}"

def truncate_to_word_count(text: str, min_words=100, max_words=200) -> str:
    """按汉字字符数截断文本"""
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

# ==================== API 配置 ====================
QWEN_API_KEY = os.getenv("QWEN_API_KEY", "sk-7bc542dd1d4d48378883befa47d91d43")  # ← 替换为你的 Key
QWEN_API_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"


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
hotel_nickname = st.sidebar.text_input("助手昵称", st.session_state.hotel_nickname)
if st.sidebar.button("💾 保存配置"):
    st.session_state.hotel_name = hotel_name.strip() or "未命名酒店"
    st.session_state.hotel_nickname = hotel_nickname.strip() or "助手"
    st.sidebar.success("✅ 配置已保存")

# ==================== 主页面逻辑 ====================

# ============ 1. 携程评分计算器（完全保留您提供的逻辑） ============
if page == "📊 携程评分提升计算器":
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

# ============ 2. 美团评分计算器（完全保留您提供的逻辑） ============
elif page == "📊 美团评分提升计算器":
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

# ============ 3. 评论维度分析（自动生成分析文本） ============
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
                        st.subheader("📋 评分详情（文本列表）")
                        # 将树状图替换为文本列表
                        st.markdown("#### 所有维度评分：")
                        for dimension, score in all_scores.items():
                            color = "🟢" if score >= 4.78 else "🔴"
                            st.markdown(f"{color} **{dimension}**: {score:.2f}")

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
    st.title("智能评论回复生成器")

    # ====== 🔐 安全读取 API Key（推荐方式）======
    try:
        QWEN_API_KEY = st.secrets["QWEN_API_KEY"]
    except KeyError:
        QWEN_API_KEY = os.getenv("QWEN_API_KEY")  # 本地开发时可用环境变量回退

    if not QWEN_API_KEY or not QWEN_API_KEY.startswith("sk-"):
        st.warning("⚠️ 请设置有效的 Qwen API Key")
        st.markdown("""
        **设置方法：**
        1. 在 Streamlit Cloud 的应用设置中打开 **Secrets**；
        2. 添加：`QWEN_API_KEY = "sk-你的密钥"`；
        3. 重新部署。
        """)
        st.stop()  # 阻止后续执行
    # =====================================

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
                    st.session_nickname,
                    review_source
                )
                raw_reply = call_qwen_api(prompt, api_key=QWEN_API_KEY)
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
                    st.rerun()  # 替代已弃用的 st.experimental_rerun()

# ==================== 尾部信息 ====================
st.sidebar.divider()
st.sidebar.caption("© 2025 酒店运营工具")

