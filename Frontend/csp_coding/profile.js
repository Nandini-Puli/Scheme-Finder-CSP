"use strict";

const API_BASE = "http://127.0.0.1:5000/api";
const SECTION_FIELDS = {
    education: ["qualification_level", "institution_name", "course_name", "field_of_study", "graduation_year", "grade_or_cgpa"],
    employment: ["employment_status", "employer_name", "job_title", "work_experience_years", "monthly_salary"],
    location: ["address_line", "district", "city", "state", "pincode"],
    income: ["annual_income", "income_source", "family_income", "ration_card_type"]
};
const PERSONAL_FIELDS = ["full_name", "email", "mobile_number", "date_of_birth", "gender", "state", "category", "district", "annual_income"];
let profileData = {};
let activeSection = "personal";

function byId(id) { return document.getElementById(id); }

function safeText(value, fallback = "Not provided") {
    return value === null || value === undefined || String(value).trim() === ""
        ? fallback : String(value).trim();
}

function setStatus(message, isError = false) {
    const el = byId("statusMessage");
    if (!el) return;
    el.textContent = message || "";
    el.classList.toggle("error", Boolean(isError));
}

async function api(path, options = {}) {
    const response = await fetch(`${API_BASE}${path}`, {
        credentials: "include",
        ...options,
        headers: { "Accept": "application/json", ...(options.headers || {}) }
    });
    const data = await response.json().catch(() => ({}));
    if (response.status === 401) {
        throw new Error("Your session has expired. Please log in again. Your saved profile remains in the database.");
    }
    if (!response.ok) throw new Error(data.message || `Request failed (${response.status}).`);
    return data;
}


function setFormValues(formId, values) {
    const form = byId(formId);
    if (!form || !values || typeof values !== "object") return;

    for (const input of form.elements) {
        if (!input.name || !(input.name in values)) continue;

        const value = values[input.name];

        if (value === null || value === undefined || value === "") {
            input.value = "";
            continue;
        }

        if (input.type === "date") {
            const text = String(value).trim();
            let dateValue = "";

            // Format: YYYY-MM-DD or ISO datetime
            if (/^\d{4}-\d{2}-\d{2}/.test(text)) {
                dateValue = text.slice(0, 10);
            }
            // Format: Thu, 31 May 2007 00:00:00 GMT
            else {
                const parsedDate = new Date(text);

                if (!Number.isNaN(parsedDate.getTime())) {
                    dateValue = [
                        parsedDate.getUTCFullYear(),
                        String(parsedDate.getUTCMonth() + 1).padStart(2, "0"),
                        String(parsedDate.getUTCDate()).padStart(2, "0")
                    ].join("-");
                }
            }

            input.value = dateValue;
        } else {
            input.value = String(value);
        }
    }
}


function readForm(formId) {
    const form = byId(formId);
    const values = {};
    if (!form) return values;
    [...form.elements].forEach(input => {
        if (!input.name) return;
        let value = input.value.trim();
        if (value === "") value = null;
        else if (input.type === "number") value = Number(value);
        values[input.name] = value;
    });
    return values;
}

function displayProfile(data) {
    profileData = data || {};
    const fullName = safeText(data.full_name, "User");
    byId("topProfileName").textContent = fullName;
    byId("profileHeading").textContent = fullName;
    byId("profileCategory").textContent = safeText(data.category, "Category not provided");

    const state = safeText(data.state, "");
    const district = safeText(data.district, "");
    byId("profileLocation").textContent =
        [district, state].filter(v => v && v !== "Not provided").join(", ") || "Location not provided";

    byId("completionProgress").textContent = `${Number(data.profile_completion || 0)}%`;
    byId("completionMessage").innerHTML = Number(data.profile_completion || 0) >= 100
        ? "Your profile is complete.<br>Keep it updated for scheme recommendations."
        : "Complete the missing fields.<br>Saved details will stay available after login.";

    const personal = {
        ...data,
        date_of_birth: data.date_of_birth ?? data.dob ?? "",
        category: data.category ?? ""
    };
    setFormValues("personalForm", personal);

    for (const section of Object.keys(SECTION_FIELDS)) {
        const sectionData = data[section];
        console.log(`${section.toUpperCase()} data returned by API:`, sectionData);
        setFormValues(`${section}Form`, sectionData && typeof sectionData === "object" ? sectionData : {});
    }

    byId("summaryEducation").textContent = safeText(data.education?.qualification_level);
    byId("summaryEmployment").textContent = safeText(data.employment?.employment_status);

    const income = data.income?.annual_income ?? data.annual_income;
    byId("summaryIncome").textContent =
        income !== null && income !== undefined && income !== "" ? `₹${income}` : "Not provided";

    const location = data.location || {};
    byId("summaryLocation").textContent =
        [location.city, location.district, location.state]
            .filter(v => v !== null && v !== undefined && String(v).trim() !== "")
            .join(", ") || "Not provided";
}

async function loadProfile(showMessage = true) {
    if (showMessage) setStatus("Loading saved profile...");
    try {
        const data = await api("/user/profile");
        displayProfile(data);
        if (showMessage) setStatus("Your saved profile has been loaded.");
        return data;
    } catch (error) {
        setStatus(error.message, true);
        if (error.message.includes("log in again")) byId("profileHeading").textContent = "Please log in";
        throw error;
    }
}

function showSection(section) {
    activeSection = section;
    document.querySelectorAll(".profile-menu-item").forEach(button => {
        button.classList.toggle("active", button.dataset.section === section);
    });
    document.querySelectorAll("[data-panel]").forEach(panel => {
        panel.hidden = panel.dataset.panel !== section;
    });
    setStatus("");
}

async function saveSection(section) {
    const button = document.querySelector(`[data-save="${section}"]`);
    if (button) button.disabled = true;
    setStatus(`Saving ${section} details...`);

    try {
        const payload = section === "personal"
            ? { personal: readForm("personalForm") }
            : { [section]: readForm(`${section}Form`) };

        const saved = await api("/user/profile", {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        console.log(`${section} save response:`, saved);

        // Always refresh from the database; the GET response is the source of truth.
        const updatedProfile = await api("/user/profile");
        if (section !== "personal" &&
            (!updatedProfile[section] || typeof updatedProfile[section] !== "object")) {
            throw new Error(`The profile API response is missing the "${section}" object.`);
        }
        displayProfile(updatedProfile);
        setStatus(`${section[0].toUpperCase() + section.slice(1)} details saved successfully.`);
    } catch (error) {
        console.error(`Error saving ${section} details:`, error);
        setStatus(error.message || "Could not save details.", true);
    } finally {
        if (button) button.disabled = false;
    }
}

async function loadDocuments() {
    const list = byId("documentList");
    list.replaceChildren();
    try {
        const data = await api("/user/documents");
        const documents = Array.isArray(data.documents) ? data.documents : [];
        if (!documents.length) {
            const p = document.createElement("p");
            p.className = "empty-message";
            p.textContent = "No documents have been uploaded yet.";
            list.appendChild(p);
            return;
        }
        documents.forEach(doc => {
            const row = document.createElement("div");
            row.className = "document";
            const name = document.createElement("div");
            name.className = "document-name";
            const check = document.createElement("span");
            check.className = "check";
            check.innerHTML = '<i class="fa-solid fa-check"></i>';
            const label = document.createElement("span");
            label.textContent = safeText(doc.document_name, doc.original_filename || "Document");
            name.append(check, label);

            const download = document.createElement("button");
            download.className = "document-download";
            download.type = "button";
            download.textContent = "Download";
            download.addEventListener("click", () => {
                window.location.href = `${API_BASE}/user/documents/${encodeURIComponent(doc.document_id)}/download`;
            });
            row.append(name, download);
            list.appendChild(row);
        });
    } catch (error) {
        const p = document.createElement("p");
        p.className = "empty-message";
        p.textContent = error.message || "Unable to load documents.";
        list.appendChild(p);
    }
}

async function loadUnreadCount() {
    try {
        const data = await api("/user/notifications/unread-count");
        const count = Number(data.unread_count || 0);
        const badge = byId("notificationBadge");
        badge.textContent = count > 99 ? "99+" : String(count);
        badge.hidden = count <= 0;
    } catch (error) {
        console.warn("Could not load unread notification count:", error);
    }
}

async function loadNotifications() {
    const list = byId("notificationList");
    list.replaceChildren();
    try {
        const data = await api("/user/notifications");
        const notifications = Array.isArray(data.notifications) ? data.notifications : [];
        if (!notifications.length) {
            const p = document.createElement("p");
            p.className = "empty-message";
            p.textContent = "No notifications yet.";
            list.appendChild(p);
            return;
        }
        notifications.forEach(item => {
            const row = document.createElement("div");
            row.className = `notification-row${Number(item.is_read) === 0 ? " unread" : ""}`;
            const title = document.createElement("strong");
            title.textContent = safeText(item.title, "Notification");
            const message = document.createElement("p");
            message.textContent = safeText(item.message, "");
            row.append(title, message);

            if (Number(item.is_read) === 0) {
                const read = document.createElement("button");
                read.type = "button";
                read.textContent = "Mark as read";
                read.addEventListener("click", async () => {
                    read.disabled = true;
                    try {
                        await api(`/user/notifications/${encodeURIComponent(item.notification_id)}/read`, { method: "POST" });
                        await loadNotifications();
                        await loadUnreadCount();
                    } catch (error) {
                        read.disabled = false;
                        alert(error.message || "Could not mark notification as read.");
                    }
                });
                row.appendChild(read);
            }
            list.appendChild(row);
        });
    } catch (error) {
        const p = document.createElement("p");
        p.className = "empty-message";
        p.textContent = error.message || "Unable to load notifications.";
        list.appendChild(p);
    }
}

function toggleNotifications() {
    const panel = byId("notificationPanel");
    panel.hidden = !panel.hidden;
    if (!panel.hidden) loadNotifications();
}

function toggleSidebar() {
    const sidebar = byId("sidebar");
    const main = byId("main");
    const topbar = document.querySelector(".topbar");
    sidebar.classList.toggle("collapsed");
    const collapsed = sidebar.classList.contains("collapsed");
    main.style.marginLeft = collapsed ? "80px" : "260px";
    topbar.style.left = collapsed ? "80px" : "260px";
}

document.querySelectorAll(".profile-menu-item").forEach(button => {
    button.addEventListener("click", () => showSection(button.dataset.section));
});
document.querySelectorAll(".save-section").forEach(button => {
    button.addEventListener("click", () => saveSection(button.dataset.save));
});
byId("notificationButton").addEventListener("click", toggleNotifications);
byId("closeNotifications").addEventListener("click", () => { byId("notificationPanel").hidden = true; });
byId("refreshDocuments").addEventListener("click", loadDocuments);
byId("editCurrentSection").addEventListener("click", () => {
    const panel = document.querySelector(`[data-panel="${activeSection}"]`);
    panel?.scrollIntoView({ behavior: "smooth", block: "start" });
    panel?.querySelector("input,select,textarea")?.focus();
});
document.querySelectorAll(".summary-item").forEach((item, index) => {
    const sections = ["education", "employment", "income", "location"];
    item.addEventListener("click", () => showSection(sections[index]));
});

loadProfile();
loadDocuments();
loadUnreadCount();
