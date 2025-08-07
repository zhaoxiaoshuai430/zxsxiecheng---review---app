import streamlit as st
st.write("Hello, I'm deploying!")
# -*- coding: utf-8 -*-
"""
🏨 酒店运营一体化系统
功能：携程/美团评分计算 + 评论维度分析 + 智能评论回复
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
import math 
from datetime import datetime
import os

# 读取环境变量中的 API 密钥
QWEN_API_KEY = os.getenv("QWEN_API_KEY")

if not QWEN_API_KEY:
    st.error("❌ 未设置 QWEN_API_KEY！请在 Streamlit Cloud 后台配置 Secrets。")
    st.stop()

# ==================== 页面配置 ====================
st.set_page_config(page_title="Hotel OTA", layout="centered")

# ==================== 初始化 session_state ====================
if 'history' not in st.session_state:
    st.session_state.history = []

if 'hotel_name' not in st.session_state:
    st.session_state.hotel_name = "星辰花园酒店"
if 'hotel_nickname' not in st.session_state:
    st.session_state.hotel_nickname = "小油"

# ==================== 工具函数 ====================

def to_excel(df):
    """将 DataFrame 转为 Excel 的 bytes 数据"""
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='分析数据')
    return output.getvalue()

def calculate_time_and_rank_weighted_score(df, score_col, date_col="入住时间"):
    """基于时间衰减和评分权重的加权平均分"""
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

def extract_aspects_and_sentiment(review: str) -> dict:
    """提取评论维度与情感"""
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
    """生成给大模型的提示词"""
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
    """调用通义千问API"""
    # 从环境变量获取 API Key
    api_key = os.getenv("QWEN_API_KEY")
    if not api_key:
        return "❌ 未设置 QWEN_API_KEY 环境变量，请在 .env 文件中配置。"

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
# ✅ 使用环境变量，不再硬编码密钥
QWEN_API_KEY = os.getenv("QWEN_API_KEY")
QWEN_API_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"

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

# -----------------------------
# 🚀 主页面逻辑
# -----------------------------

# ============ 1. 携程评分计算器 ============
if page == "📊 携程评分计算器":
    st.title("携程酒店评分提升计算器 ")

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
    st.title("美团酒店评分提升计算器 ")

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

# ============ 3. 评论维度分析 ============
elif page == "📈 评论维度分析":
    st.title("📈 评论维度分析（支持 Excel 上传）")

    st.markdown("""
    上传包含以下列的 Excel 文件：
    - 环境、设施、服务、卫生、性价比、位置
    - 入住时间（格式：YYYY-MM-DD）
    """)

    with st.expander("📄 示例格式"):
        st.write(pd.DataFrame({
            '环境': [4.8], '设施': [4.5], '服务': [4.2], '卫生': [4.6],
            '性价比': [4.7], '位置': [4.9], '入住时间': ['2025-07-01']
        }))

    uploaded_file = st.file_uploader("上传评论数据 (.xlsx)", type=["xlsx"])

    # 改进建议库
    IMPROVEMENT_SUGGESTIONS = {
        '服务': """
🔹 **服务优化建议**：
- 加强员工服务意识培训，提升响应速度与礼貌用语；
- 建立客户反馈快速响应机制，及时处理投诉；
- 推出个性化服务（如生日祝福、欢迎茶饮）提升体验。
        """,
        '设施': """
🔹 **设施优化建议**：
- 定期检查设备老化情况（如空调、热水器、Wi-Fi）；
- 升级客房智能设备（如智能门锁、语音控制）；
- 增加公共区域设施（如充电站、自助洗衣、休闲区）。
        """,
        '卫生': """
🔹 **卫生优化建议**：
- 强化清洁流程标准，实施“三级检查”制度；
- 使用可视化清洁记录（如拍照上传系统）；
- 增加消毒频次，尤其高频接触区域（门把手、电梯按钮）。
        """,
        '环境': """
🔹 **环境优化建议**：
- 优化隔音设计，减少噪音干扰；
- 增加绿植与景观布置，提升舒适度；
- 控制公共区域灯光与音乐，营造温馨氛围。
        """,
        '位置': """
🔹 **位置优化建议**：
- 虽位置难以改变，但可优化交通接驳服务；
- 提供详细出行指南（地铁、打车、步行路线）；
- 与周边餐饮/景点合作推出优惠联动套餐。
        """,
        '性价比': """
🔹 **性价比优化建议**：
- 优化价格策略，推出淡季优惠、连住折扣；
- 提升服务与设施感知价值（如免费早餐、欢迎水果）；
- 明确宣传核心优势，增强"物有所值"感知。
        """
    }

    if uploaded_file:
        try:
            df = pd.read_excel(uploaded_file)
            dimensions = ['环境', '设施', '服务', '卫生', '性价比', '位置']
            valid_dims = [d for d in dimensions if d in df.columns]

            if "入住时间" not in df.columns:
                st.error("❌ 缺少 '入住时间' 列")
            elif not valid_dims:
                st.error("❌ 未找到有效维度列")
            else:
                avg_scores = {}
                for dim in valid_dims:
                    score = calculate_time_and_rank_weighted_score(df, dim, "入住时间")
                    avg_scores[dim] = score

                avg_scores = pd.Series(avg_scores)
                overall_score = avg_scores.mean().round(2)

                fig, ax = plt.subplots(figsize=(8, 5))
                colors = ['green' if v >= 4.78 else 'orange' for v in avg_scores]
                avg_scores.plot(kind='bar', ax=ax, color=colors, alpha=0.8)
                for i, v in enumerate(avg_scores):
                    color = 'green' if v >= 4.78 else 'orange'
                    ax.text(i, v + 0.05, f"{v:.2f}", ha='center', fontsize=9, color=color, fontweight='bold')
                plt.xticks(rotation=45)
                plt.ylim(0, 5)
                plt.ylabel("最终评分")
                plt.title("各维度评分对比")
                plt.tight_layout()
                st.pyplot(fig)

                st.metric("🏆 综合评分", f"{overall_score:.2f} ⭐")

                excellent = avg_scores[avg_scores >= 4.78]
                needs_improvement = avg_scores[avg_scores < 4.78]

                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("### ✅ 优秀项")
                    if len(excellent) == 0:
                        st.markdown("暂无优秀项")
                    else:
                        for dim, score in excellent.items():
                            st.markdown(f"🟢 **{dim}**: {score:.2f}")

                with col2:
                    st.markdown("### ⚠️ 待改进项")
                    if len(needs_improvement) == 0:
                        st.markdown("所有维度均表现优秀！")
                    else:
                        for dim, score in needs_improvement.items():
                            st.markdown(f"🟠 **{dim}**: {score:.2f}")

                st.markdown("---")
                st.subheader("📝 自动分析结论与优化建议")

                conclusion_parts = []
                if overall_score >= 4.5:
                    conclusion_parts.append(f"整体表现优秀，综合评分为 **{overall_score:.2f}**，客户满意度较高。")
                elif overall_score >= 4.0:
                    conclusion_parts.append(f"整体表现良好，综合评分为 **{overall_score:.2f}**，存在提升空间。")
                else:
                    conclusion_parts.append(f"整体表现有待提升，综合评分为 **{overall_score:.2f}**，需重点关注。")

                if len(excellent) > 0:
                    good_dims = "、".join(excellent.index.tolist())
                    conclusion_parts.append(f"优势维度为：**{good_dims}**，继续保持。")

                if len(needs_improvement) > 0:
                    st.markdown("### 🔧 重点改进建议")
                    for dim in needs_improvement.index:
                        suggestion = IMPROVEMENT_SUGGESTIONS.get(dim, f"🔹 **{dim}**: 建议加强相关方面管理与投入。")
                        st.markdown(suggestion)
                    weak_dims = "、".join(needs_improvement.index.tolist())
                    conclusion_parts.append(f"需重点改进：**{weak_dims}**。")
                else:
                    conclusion_parts.append("所有维度均达到优秀水平，继续保持服务品质。")

                final_conclusion = "。".join(conclusion_parts) + "。"
                st.markdown(f"> {final_conclusion}")

                excel_data = to_excel(df)
                b64 = base64.b64encode(excel_data).decode()
                href = f'<a href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{b64}" download="评论分析数据.xlsx">📥 下载原始数据</a>'
                st.markdown(href, unsafe_allow_html=True)

        except Exception as e:
            st.error(f"❌ 数据处理出错：{str(e)}")
            st.info("请检查 Excel 文件格式是否正确，评分列是否为数值类型。")

# ============ 4. 智能评论回复 ============
elif page == "💬 智能评论回复":
    st.title("智能评论回复生成器")

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
if page == "💬 智能评论回复" and not QWEN_API_KEY:

    st.warning("⚠️ 请设置环境变量 `QWEN_API_KEY`。详情见 README.md")




