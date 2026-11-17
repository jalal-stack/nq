import { describe, expect, it } from "vitest";
import { wsUrl } from "./api";
import { checkLabel, fmtAge, fmtNum, fmtPct, fmtUsd, humanize } from "./format";

describe("format", () => {
  it("formats currency and handles missing values", () => {
    expect(fmtUsd(5000)).toBe("$5,000.00");
    expect(fmtUsd("-12.345")).toBe("-$12.35");
    expect(fmtUsd(null)).toBe("—");
  });
  it("formats percentages, numbers and ages", () => {
    expect(fmtPct(0.5)).toBe("50.0%");
    expect(fmtPct(null)).toBe("—");
    expect(fmtNum("1.234", 1)).toBe("1.2");
    expect(fmtAge(30)).toBe("30s");
    expect(fmtAge(600)).toBe("10m");
    expect(fmtAge(7200)).toBe("2h");
    expect(fmtAge(null)).toBe("—");
  });
  it("humanizes risk codes", () => {
    expect(humanize("stop_too_wide")).toBe("Stop too wide");
    expect(checkLabel("session_closed")).toBe("Trading session");
    expect(checkLabel("brand_new_check")).toBe("Brand new check");
  });
});

describe("wsUrl", () => {
  it("derives a ws:// URL from the API base", () => {
    expect(wsUrl("/ws/market", { symbol: "BTC/USDT" })).toBe(
      "ws://127.0.0.1:8000/api/v1/ws/market?symbol=BTC%2FUSDT",
    );
  });
});
