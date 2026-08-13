/**
 * @note 所有文字输入框的最大字符数上限集中在此处。
 *       这些数值必须与后端 backend/utils/utils_require.py 中的限制保持一致，
 *       这样用户在前端就会被 maxLength 拦下，而不会在提交后才被服务端拒绝。
 */

export const INPUT_LIMITS = {
  // 账号相关
  USERNAME: 20,
  EMAIL: 40,
  PASSWORD: 64,
  VERIFICATION_CODE: 6,

  // 个人主页 / 资料
  SIGNATURE: 100, // 对齐 UserProfile.signature
  AVATAR_URL: 100, // 对齐 UserProfile.avatar_url
  LONG_TEXT: 1000, // 个人简介 / 科研经历 / 荣誉 / 项目经历 等长文本

  // 导师 / 论文
  NAME: 20, // 导师中英文名、实名
  RESEARCH_DIRECTION: 200,
  MENTOR_PROFILE: 1000, // 导师画像
  PAPER_TITLE: 200,
  PAPER_ABSTRACT: 3000,
  AUTHOR_NAMES: 1000,

  // 搜索 / 过滤关键词（需能容纳完整论文标题，故与 PAPER_TITLE 对齐）
  KEYWORD: 200,
} as const;

export default INPUT_LIMITS;
