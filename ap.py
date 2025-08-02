import streamlit as st
import math

# ========== 页面配置 ==========
st.set_page_config(page_title="酒店评分计算器", layout="centered")

# ========== 页面选择器 ==========
st.sidebar.title("🏨 酒店评分计算器")
page = st.sidebar.radio("选择平台", ["携程评分计算器", "美团评分计算器"])

# ========== 公共计算函数 ==========
def calculate_required_reviews(weighted_current_score, score_past, target_score, reviews_recent, reviews_past_count):
    """
    通用计算函数：
    - weighted_current_score: 当前加权总评分
    - score_past: 历史评分（三年前 / 一年前）
    - target_score: 目标评分
    - reviews_recent: 近期评论数（三年 / 一年）
    - reviews_past_count: 历史评论数
    """
    # 反推近期真实评分：加权 = 0.9 * recent + 0.1 * past
    current_score_recent = (weighted_current_score - score_past * 0.1) / 0.9

    if not (0 <= current_score_recent <= 5.0):
        raise ValueError("输入的【加权评分】与【历史评分】组合不合理，反推出的【近期评分】超出 0~5 范围。")

    # 当前近期总得分
    current_total_recent_score = current_score_recent * reviews_recent

    # 计算目标所需的“近期评分”
    required_recent_score = (target_score - score_past * 0.1) / 0.9

    if required_recent_score >= 5.0:
        raise ValueError("目标评分过高，即使全为5星也无法达到。")

    # 解方程：(A + 5R) / (N + R) >= req  =>  R >= (req*N - A) / (5 - req)
    N = reviews_recent
    A = current_total_recent_score
    req = required_recent_score

    numerator = req * N - A
    denominator = 5.0 - req

    if numerator <= 0:
        return 0, current_score_recent  # 已达标

    if denominator <= 0:
        raise ValueError("目标评分不合法，导致分母非正。")

    required_5_star = numerator / denominator
    required_5_star = math.ceil(required_5_star)

    return required_5_star, current_score_recent


# ========== 携程页面 ==========
def xiecheng_page():
    st.title("携程酒店评分提升计算器 ")
    st.markdown("""
    - ✅ 输入【当前加权综合评分】与【三年前评分】
    - ✅ 自动反推【近三年真实评分】
    - ✅ 支持【三年前评论数 10:1 折算】
    - ✅ 精准计算所需 5 星好评数量
    """)

    col1, col2, col3 = st.columns(3)

    with col1:
        st.subheader("📌 评分输入")
        weighted_current_score = st.number_input(
            "当前加权综合评分",
            min_value=0.0,
            max_value=5.0,
            value=4.52,
            step=0.01,
            key="xiecheng_weighted"
        )
        score_3_years_ago = st.number_input(
            "三年前评分",
            min_value=0.0,
            max_value=5.0,
            value=4.70,
            step=0.01,
            key="xiecheng_past"
        )

    with col2:
        st.subheader("📝 评论数量")
        reviews_last_3_years = st.number_input(
            "近三年评价数",
            min_value=0,
            value=500,
            step=1,
            key="xiecheng_recent"
        )
        reviews_before_3_years = st.number_input(
            "三年前评价数",
            min_value=0,
            value=300,
            step=1,
            key="xiecheng_past_count"
        )

    with col3:
        st.subheader("🎯 目标设置")
        target_score = st.number_input(
            "目标评分",
            min_value=0.0,
            max_value=5.0,
            value=4.80,
            step=0.01,
            key="xiecheng_target"
        )

    # === 计算与结果 ===
    try:
        required_5_star, inferred_recent_score = calculate_required_reviews(
            weighted_current_score, score_3_years_ago, target_score,
            reviews_last_3_years, reviews_before_3_years
        )

        st.success(f"✅ 反推出近三年真实评分为：**{inferred_recent_score:.3f} 分**")

        if required_5_star == 0:
            st.info(f"🎉 当前评分已达到或超过目标 **{target_score:.2f}** 分，无需新增好评！")
        else:
            st.warning(f"📈 要达到 **{target_score:.2f}** 分，还需要至少 **{required_5_star}** 条 5 星好评")

        with st.expander("🔍 查看详细计算过程"):
            effective_old = reviews_before_3_years / 10.0
            st.write(f"""
            - 当前加权评分：{weighted_current_score:.2f}
            - 三年前评分：{score_3_years_ago:.2f}
            - 反推近三年评分：{inferred_recent_score:.3f}
            - 近三年评价数：{reviews_last_3_years}
            - 三年前评价数：{reviews_before_3_years}（按 10:1 折算 → 等效 {effective_old:.1f} 条）
            - 目标评分：{target_score:.2f}
            - 需新增 5 星评论：{required_5_star} 条
            """)

    except ValueError as e:
        st.error(f"❌ 计算错误：{str(e)}")


# ========== 美团页面 ==========
def meituan_page():
    st.title("美团酒店评分提升计算器 ")
    st.markdown("""
    - ✅ 输入【当前加权综合评分】与【一年前评分】
    - ✅ 自动反推【近一年真实评分】
    - ✅ 支持【一年前评论数 10:1 折算】
    - ✅ 精准计算所需 5 星好评数量
    """)

    col1, col2, col3 = st.columns(3)

    with col1:
        st.subheader("📌 评分输入")
        weighted_current_score = st.number_input(
            "当前加权综合评分",
            min_value=0.0,
            max_value=5.0,
            value=4.52,
            step=0.01,
            key="meituan_weighted"
        )
        score_1_year_ago = st.number_input(
            "一年前评分",
            min_value=0.0,
            max_value=5.0,
            value=4.60,
            step=0.01,
            key="meituan_past"
        )

    with col2:
        st.subheader("📝 评论数量")
        reviews_last_1_year = st.number_input(
            "近一年评价数",
            min_value=0,
            value=300,
            step=1,
            key="meituan_recent"
        )
        reviews_before_1_year = st.number_input(
            "一年前评价数",
            min_value=0,
            value=500,
            step=1,
            key="meituan_past_count"
        )

    with col3:
        st.subheader("🎯 目标设置")
        target_score = st.number_input(
            "目标评分",
            min_value=0.0,
            max_value=5.0,
            value=4.80,
            step=0.01,
            key="meituan_target"
        )

    # === 计算与结果 ===
    try:
        required_5_star, inferred_recent_score = calculate_required_reviews(
            weighted_current_score, score_1_year_ago, target_score,
            reviews_last_1_year, reviews_before_1_year
        )

        st.success(f"✅ 反推出近一年真实评分为：**{inferred_recent_score:.3f} 分**")

        if required_5_star == 0:
            st.info(f"🎉 当前评分已达到或超过目标 **{target_score:.2f}** 分，无需新增好评！")
        else:
            st.warning(f"📈 要达到 **{target_score:.2f}** 分，还需要至少 **{required_5_star}** 条 5 星好评")

        with st.expander("🔍 查看详细计算过程"):
            effective_old = reviews_before_1_year / 10.0
            st.write(f"""
            - 当前加权评分：{weighted_current_score:.2f}
            - 一年前评分：{score_1_year_ago:.2f}
            - 反推近一年评分：{inferred_recent_score:.3f}
            - 近一年评价数：{reviews_last_1_year}
            - 一年前评价数：{reviews_before_1_year}（按 10:1 折算 → 等效 {effective_old:.1f} 条）
            - 目标评分：{target_score:.2f}
            - 需新增 5 星评论：{required_5_star} 条
            """)

    except ValueError as e:
        st.error(f"❌ 计算错误：{str(e)}")


# ========== 主程序 ==========
if page == "携程评分计算器":
    xiecheng_page()
elif page == "美团评分计算器":
    meituan_page()