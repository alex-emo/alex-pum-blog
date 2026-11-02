/* 文章页评论：验证码加载、回复定位、提交。 */
(function () {
  "use strict";

  const section = document.getElementById("comments");
  const form = document.getElementById("comment-form");
  if (!section || !form) return;

  const slug = section.dataset.slug;
  const captchaImage = document.getElementById("captcha-image");
  const captchaRefresh = document.getElementById("captcha-refresh");
  const captchaAnswer = document.getElementById("comment-captcha");
  const nameInput = document.getElementById("comment-author");
  const contentInput = document.getElementById("comment-content");
  const parentInput = document.getElementById("comment-parent");
  const submitButton = document.getElementById("comment-submit");
  const messageEl = document.getElementById("comment-msg");

  let captchaId = "";
  let replyingTo = null;

  function errorText(data) {
    const detail = data && data.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail.length && detail[0].msg) {
      return "提交内容不合规：" + detail[0].msg;
    }
    return "";
  }

  function showMessage(text, isError) {
    messageEl.textContent = text;
    messageEl.className = "form-msg " + (isError ? "err" : "ok");
  }

  async function loadCaptcha() {
    captchaImage.alt = "验证码加载中";
    try {
      const response = await fetch("/api/captcha", { credentials: "same-origin" });
      if (!response.ok) throw new Error("验证码加载失败");
      const data = await response.json();
      captchaId = data.captcha_id;
      captchaImage.src = data.image;
      captchaImage.alt = "验证码图片，点击刷新";
      captchaAnswer.value = "";
    } catch (err) {
      captchaImage.alt = "验证码加载失败，请点击刷新";
      captchaId = "";
    }
  }

  captchaImage.addEventListener("click", loadCaptcha);
  captchaRefresh.addEventListener("click", loadCaptcha);

  section.querySelectorAll(".comment-reply").forEach((button) => {
    button.addEventListener("click", () => {
      if (replyingTo === button.dataset.parent) {
        cancelReply();
        return;
      }
      replyingTo = button.dataset.parent;
      parentInput.value = replyingTo;
      showMessage("回复 @" + button.dataset.author + "（再次点击同一条可取消）", false);
      contentInput.focus();
    });
  });

  // 待审评论立即在列表里占个位，避免用户以为没提交成功
  function showPendingPreview(text) {
    const list = document.getElementById("comment-list");
    if (!list) return;
    const empty = list.querySelector(".comment-empty");
    if (empty) empty.remove();

    const article = document.createElement("article");
    article.className = "comment comment-pending";
    const head = document.createElement("header");
    head.className = "comment-head";
    const author = document.createElement("span");
    author.className = "comment-author";
    author.textContent = nameInput.value.trim();
    const badge = document.createElement("span");
    badge.className = "pending-badge";
    badge.textContent = "待审核";
    head.append(author, badge);
    const body = document.createElement("p");
    body.className = "comment-body";
    body.textContent = text;
    article.append(head, body);
    list.appendChild(article);
    article.scrollIntoView({ block: "nearest" });
  }

  function resetReply() {
    replyingTo = null;
    parentInput.value = "";
  }

  function cancelReply() {
    resetReply();
    showMessage("", false);
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (submitButton.disabled) return;

    if (!nameInput.value.trim()) {
      showMessage("请填写昵称", true);
      nameInput.focus();
      return;
    }
    if (contentInput.value.trim().length < 2) {
      showMessage("评论内容太短了", true);
      contentInput.focus();
      return;
    }
    if (!captchaId) {
      showMessage("验证码没加载出来，请点图片刷新", true);
      return;
    }
    if (!captchaAnswer.value.trim()) {
      showMessage("请输入验证码", true);
      captchaAnswer.focus();
      return;
    }

    const submitted = contentInput.value.trim();
    submitButton.disabled = true;
    showMessage("提交中…", false);

    try {
      const response = await fetch("/api/posts/" + encodeURIComponent(slug) + "/comments", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          author_name: nameInput.value.trim(),
          content: contentInput.value.trim(),
          captcha_id: captchaId,
          captcha_answer: captchaAnswer.value.trim(),
          parent_id: replyingTo ? Number(replyingTo) : null,
          website: form.querySelector('[name="website"]').value,
        }),
      });
      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        throw new Error(errorText(data) || "提交失败，请稍后再试");
      }

      contentInput.value = "";
      resetReply();          // 只清回复状态，保留成功提示
      showMessage(data.message || "提交成功", false);
      messageEl.scrollIntoView({ block: "nearest" });

      if (data.pending) {
        showPendingPreview(submitted);
        await loadCaptcha();
      } else {
        // 无需审核：直接刷新显示新评论
        location.hash = "#comments";
        location.reload();
      }
    } catch (err) {
      showMessage(err.message || "网络错误，请稍后再试", true);
      loadCaptcha();
    } finally {
      submitButton.disabled = false;
    }
  });

  loadCaptcha();
})();
