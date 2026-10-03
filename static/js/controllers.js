import { Application, Controller } from "https://unpkg.com/@hotwired/stimulus@3.2.2/dist/stimulus.js"

const application = Application.start()

class FlashController extends Controller {
  static targets = ["item"]
  connect() {
    window.setTimeout(() => {
      this.itemTargets.forEach((el) => {
        el.style.opacity = "0"
        el.style.transition = "opacity .4s"
      })
    }, 4000)
  }
}

class FormHintController extends Controller {
  static targets = ["status", "hint"]
  connect() {
    this.update()
    this.statusTarget?.addEventListener("change", () => this.update())
  }
  update() {
    if (!this.hasHintTarget || !this.hasStatusTarget) return
    if (this.statusTarget.value === "drawn") {
      this.hintTarget.textContent =
        "当前选择「已出灰」：须存在最近批次，且峰值温度已记录并 ≥ 60℃。"
    } else if (this.statusTarget.value === "slaking") {
      this.hintTarget.textContent =
        "改为「熟化中」：若同厂另有熟化中池，须已持一张未核销邻池放行签，签将在保存时核销。"
    } else {
      this.hintTarget.textContent =
        "出灰前请确认最近熟化批次已记录峰值温度且不低于 60℃。"
    }
  }
}

class PassFormController extends Controller {
  static targets = ["target", "hot"]
  connect() {
    this.filterHot()
  }
  // 热邻池必须与目标池同厂：按目标池厂区过滤热邻下拉。
  filterHot() {
    if (!this.hasTargetTarget || !this.hasHotTarget) return
    const plant = this.targetTarget.selectedOptions[0]?.dataset.plant || ""
    let firstEnabled = null
    Array.from(this.hotTarget.options).forEach((opt) => {
      if (!opt.value) return
      const ok = !plant || opt.dataset.plant === plant
      opt.hidden = !ok
      opt.disabled = !ok
      if (ok && firstEnabled === null) firstEnabled = opt
    })
    if (plant) {
      const cur = this.hotTarget.selectedOptions[0]
      if (!cur || cur.dataset.plant !== plant) {
        this.hotTarget.value = firstEnabled ? firstEnabled.value : ""
      }
    }
  }
}

class BoardController extends Controller {
  static targets = ["drawer", "backdrop"]
  static values = { open: Boolean }

  connect() {
    if (this.openValue) this._setOpen(true)
  }

  openDrawer() {
    // Navigation still loads selected pond; keep drawer state consistent on SPA-less click
    this._setOpen(true)
  }

  closeDrawer(event) {
    if (event) event.preventDefault()
    this._setOpen(false)
    const closeLink = event?.currentTarget
    if (closeLink?.href) {
      window.location.href = closeLink.href
    } else if (this.hasBackdropTarget) {
      const base = new URL(window.location.href)
      base.searchParams.delete("pond")
      window.location.href = base.toString()
    }
  }

  _setOpen(open) {
    this.openValue = open
    if (this.hasDrawerTarget) {
      this.drawerTarget.classList.toggle("is-open", open)
      this.drawerTarget.setAttribute("aria-hidden", open ? "false" : "true")
    }
    if (this.hasBackdropTarget) {
      this.backdropTarget.classList.toggle("is-open", open)
    }
  }
}

application.register("flash", FlashController)
application.register("form-hint", FormHintController)
application.register("pass-form", PassFormController)
application.register("board", BoardController)
