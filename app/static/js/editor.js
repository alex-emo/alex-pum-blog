/* 文章编辑器：Markdown 预览、图片粘贴上传、保存/发布。 */
(function () {
  "use strict";

  const form = document.getElementById("editor-form");
  if (!form) return;

  const titleInput = document.getElementById("post-title");
  const contentInput = document.getElementById("post-content");
  const summaryInput = document.getElementById("post-summary");
  const tagsInput = document.getElementById("post-tags");
  const slugInput = document.getElementById("post-slug");
  const coverInput = document.getElementById("post-cover");
  const previewBody = document.getElementById("post-preview");
  const previewState = document.getElementById("preview-state");
  const saveState = document.getElementById("save-state");
  const noteEl = document.getElementById("post-note");
  const draftButton = document.getElementById("save-draft");
  const publishButton = document.getElementById("save-publish");
  const deleteButton = document.getElementById("delete-post");

  let postId = form.dataset.postId ? Number(form.dataset.postId) : null;
  let currentStatus = "draft";
  let dirty = false;
  let saving = false;
  let previewTimer = null;

  /* ---------------------------------------------------------- 保存状态 */
  function markDirty() {
    dirty = true;
    saveState.textContent = "未保存";
  }

  function setSaved(message) {
    dirty = false;
    saveState.textContent = message || "已保存";
  }

  window.addEventListener("beforeunload", (event) => {
    if (!dirty) return;
    event.preventDefault();
    event.returnValue = "";
  });

  [titleInput, contentInput, summaryInput, tagsInput, slugInput, coverInput].forEach((el) => {
    el.addEventListener("input", () => {
      markDirty();
      if (el === contentInput) schedulePreview();
    });
  });

  /* ---------------------------------------------------------- 预览 */
  function schedulePreview() {
    clearTimeout(previewTimer);
    previewState.textContent = "渲染中…";
    previewTimer = setTimeout(renderPreview, 400);
  }

  async function renderPreview() {
    const markdown = contentInput.value;
    if (!markdown.trim()) {
      previewBody.innerHTML = '<p class="muted">预览会显示在这里。</p>';
      previewState.textContent = "";
      return;
    }
    try {
      const data = await Api.post("/api/admin/preview", { content_md: markdown });
      previewBody.innerHTML = data.html;
      // 预览里如果有数学公式，交给 MathJax 排版
      if (window.MathJax && window.MathJax.typesetPromise) {
        window.MathJax.typesetPromise([previewBody]).catch(() => {});
      }
      previewState.textContent = "";
    } catch (err) {
      previewState.textContent = "预览失败";
    }
  }

  /* ---------------------------------------------------------- 图片上传 */
  async function uploadImage(file) {
    if (!file.type.startsWith("image/")) {
      toast("只能上传图片", true);
      return;
    }
    previewState.textContent = "上传图片中…";
    try {
      const media = await Api.upload("/api/admin/media", file);
      insertAtCursor("![图片](" + media.url + ")\n");
      previewState.textContent = "图片已插入";
      toast("图片已上传");
    } catch (err) {
      previewState.textContent = "";
      toast(err.message, true);
    }
  }

  function insertAtCursor(text) {
    const start = contentInput.selectionStart || 0;
    const end = contentInput.selectionEnd || 0;
    contentInput.value = contentInput.value.slice(0, start) + text + contentInput.value.slice(end);
    const caret = start + text.length;
    contentInput.setSelectionRange(caret, caret);
    contentInput.focus();
    markDirty();
    schedulePreview();
  }

  contentInput.addEventListener("paste", (event) => {
    const items = Array.from(event.clipboardData ? event.clipboardData.items : []);
    const imageItem = items.find((item) => item.kind === "file" && item.type.startsWith("image/"));
    if (imageItem) {
      event.preventDefault();
      uploadImage(imageItem.getAsFile());
    }
  });

  contentInput.addEventListener("dragover", (event) => event.preventDefault());
  contentInput.addEventListener("drop", (event) => {
    const file = event.dataTransfer && event.dataTransfer.files && event.dataTransfer.files[0];
    if (file && file.type.startsWith("image/")) {
      event.preventDefault();
      uploadImage(file);
    }
  });

  /* ---------------------------------------------------------- 加载已有文章 */
  async function loadPost() {
    if (!postId) {
      setSaved("新文章");
      return;
    }
    try {
      const post = await Api.get("/api/admin/posts/" + postId);
      titleInput.value = post.title;
      contentInput.value = post.content_md;
      summaryInput.value = post.summary || "";
      tagsInput.value = post.tags.map((tag) => tag.name).join(", ");
      slugInput.value = post.slug;
      coverInput.value = post.cover_image || "";
      currentStatus = post.status;
      deleteButton.hidden = false;
      noteEl.textContent = "创建于 " + formatDate(post.created_at) +
        (post.published_at ? "，发布于 " + formatDate(post.published_at) : "");
      syncButtons();
      setSaved(currentStatus === "published" ? "已发布" : "草稿");
      renderPreview();
    } catch (err) {
      toast(err.message, true);
    }
  }

  /* ---------------------------------------------------------- 保存 */
  function collect() {
    const tags = tagsInput.value.split(/[,，]/).map((t) => t.trim()).filter(Boolean);
    const payload = {
      title: titleInput.value.trim(),
      content_md: contentInput.value,
      summary: summaryInput.value.trim(),
      tags,
    };
    if (slugInput.value.trim()) payload.slug = slugInput.value.trim();
    if (coverInput.value.trim()) payload.cover_image = coverInput.value.trim();
    return payload;
  }

  async function save(status) {
    if (saving) return;
    const payload = collect();
    if (!payload.title) {
      toast("先写个标题", true);
      titleInput.focus();
      return;
    }
    if (status === "published" && !payload.content_md.trim()) {
      toast("正文不能为空", true);
      contentInput.focus();
      return;
    }

    saving = true;
    draftButton.disabled = true;
    publishButton.disabled = true;
    saveState.textContent = "保存中…";

    try {
      if (postId) {
        const updated = await Api.patch("/api/admin/posts/" + postId, Object.assign(payload, { status }));
        currentStatus = updated.status;
        slugInput.value = updated.slug;
        history.replaceState(null, "", "/admin/posts/" + postId + "/edit");
      } else {
        const created = await Api.post("/api/admin/posts", Object.assign(payload, { status }));
        postId = created.id;
        currentStatus = created.status;
        slugInput.value = created.slug;
        deleteButton.hidden = false;
        history.replaceState(null, "", "/admin/posts/" + postId + "/edit");
      }
      syncButtons();
      setSaved(status === "published" ? "已发布" : "已存草稿");
      toast(status === "published" ? "已发布" : "草稿已保存");
    } catch (err) {
      saveState.textContent = "保存失败";
      toast(err.message, true);
    } finally {
      saving = false;
      draftButton.disabled = false;
      publishButton.disabled = false;
    }
  }

  function syncButtons() {
    const published = currentStatus === "published";
    publishButton.textContent = published ? "更新" : "发布";
    draftButton.textContent = published ? "转为草稿" : "存草稿";
  }

  draftButton.addEventListener("click", () => save("draft"));
  publishButton.addEventListener("click", () => save("published"));

  deleteButton.addEventListener("click", async () => {
    if (!postId) return;
    if (!confirm("删除这篇文章？操作不可撤销。")) return;
    try {
      await Api.del("/api/admin/posts/" + postId);
      dirty = false;
      location.href = "/admin/posts";
    } catch (err) {
      toast(err.message, true);
    }
  });

  document.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
      event.preventDefault();
      save(currentStatus === "published" ? "published" : "draft");
    }
  });

  loadPost();
})();
