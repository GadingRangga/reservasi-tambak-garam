document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("reservation-form");
    if (!form) return;

    const ticketPrice = Number(form.dataset.price || 25000);
    const participantsInput = document.getElementById("participants");
    const dateInput = document.getElementById("visit_date");
    const totalDisplay = document.getElementById("total-price-display");
    const quotaInfo = document.getElementById("quota-info");

    function updateTotalPrice() {
        const count = Math.max(Number(participantsInput.value || 0), 0);
        const total = count * ticketPrice;
        totalDisplay.textContent = "Rp" + total.toLocaleString("id-ID");
    }

    async function checkQuota() {
        const selectedDate = dateInput.value;
        if (!selectedDate) return;

        quotaInfo.textContent = "Mengecek sisa kuota...";
        try {
            const response = await fetch(`/api/quota?date=${encodeURIComponent(selectedDate)}`);
            const data = await response.json();
            if (!response.ok) {
                quotaInfo.textContent = data.error || "Gagal mengecek kuota.";
                return;
            }
            quotaInfo.textContent = `Sisa kuota pada ${data.date}: ${data.remaining_quota} dari ${data.max_capacity} orang.`;
        } catch (err) {
            quotaInfo.textContent = "Tidak dapat memuat informasi kuota.";
        }
    }

    participantsInput.addEventListener("input", updateTotalPrice);
    dateInput.addEventListener("change", checkQuota);
    updateTotalPrice();
});