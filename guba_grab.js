/**
 * 股吧本地抓取工具 — Chrome Console 粘贴即用
 * 
 * 使用步骤：
 * 1. 打开 Chrome，访问 https://guba.eastmoney.com/list,sh000001.html
 * 2. F12 打开控制台
 * 3. 复制粘贴本文件全部内容，回车
 * 4. JSON 自动复制到剪贴板
 * 5. 粘贴到任意地方保存（或让屁包读取剪贴板）
 */

(function() {
  const PAGE_NAME = document.title || 'unknown';
  
  if (typeof window.article_list === 'undefined') {
    console.error('❌ article_list 不存在，请确认页面已加载完毕');
    return;
  }
  
  const posts = window.article_list.re.map(p => ({
    title: p.post_title || '',
    click: p.post_click_count || 0,
    comment: p.post_comment_count || 0,
    time: p.post_publish_time || '',
    user_id: p.post_user?.user_id || '',
  }));
  
  const result = JSON.stringify(posts, null, 2);
  console.log(`✅ ${PAGE_NAME}: ${posts.length} 条帖子已复制到剪贴板`);
  
  // 复制到剪贴板
  copy(result);
  
  // 同时输出前5条预览
  console.table(posts.slice(0, 5).map(p => ({
    标题: p.title.slice(0, 40),
    点击: p.click,
    评论: p.comment,
    时间: p.time,
  })));
  
  console.log('\n📋 JSON已在剪贴板，可直接粘贴到文件或发送给屁包');
})();
