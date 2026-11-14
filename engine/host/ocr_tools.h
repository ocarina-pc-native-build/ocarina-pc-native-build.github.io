/* Ocarina Reborn's transient photo tools and wallet action protocol.
   Kept out of vk_api.h: these tools do not change compiled shaders. */
#pragma once
enum {
    OCR_OPT_PHOTO = 4200,
    OCR_OPT_PHOTO_READY = 4201,
    OCR_RUPEE_ACTION = 500,
    OCR_RUPEE_CHOICES = 6
};
static inline int ocr_rupee_amount(int choice) {
    static const int amounts[OCR_RUPEE_CHOICES] = {1, 10, 50, 100, 500, 9999};
    return choice >= 0 && choice < OCR_RUPEE_CHOICES ? amounts[choice] : 0;
}
static inline int ocr_rupee_delta(int choice, int current, int capacity) {
    if (current < 0 || capacity < 1 || capacity > 9999 || current >= capacity) return 0;
    const int want = ocr_rupee_amount(choice), room = capacity - current;
    return want < room ? want : room;
}
