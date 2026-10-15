"""P9-I10 accessibility and report-scale regressions.

No real image, camera or independent physical calibration acceptance is implied.
"""
import inspect
import json
import pytest

from aiforensics.ui_readability import (
    PAGE_SIZE, MAX_PREVIEW_CHARS, filter_findings, finding_page,
    format_finding, graph_point, clamp_zoom,
)
from aiforensics.science_panel_ui import show_holdout, show_residuals
from aiforensics.review_ui import ReviewWindow


def synthetic(n=1000):
    return [{"record_id":f"P8-E03/obs-{i:04d}",
             "module_id":"P8-E03" if i%2 else "P1-G02",
             "physical_claim":f"model-{i}",
             "measurement":{"measured":10.,"predicted":9.,
                            "signed_residual":1.,"unit":"px",
                            "confidence_interval_95_for_residual":None},
             "uncertainty":{"residual_std":0.5},
             "single_test":{"state":"INDETERMINATE" if i%2 else
                            "CONSISTENT_UNDER_ASSUMPTIONS",
                            "p_value_two_sided":None},
             "dependency":{"component_id":"dep1", "component_state":"NOT_TESTED",
                           "holm_adjusted_p_value":None},
             "assumptions":[{"name":"scene", "status":"unknown","source":"toy"}],
             "explanation":["No calibrated observation."],
             "provenance":{"source_id":"toy"}} for i in range(n)]


def test_paging_1000_records_no_truncation():
    data=synthetic()
    assert PAGE_SIZE==40
    ids=[]
    for page in range(25):
        part=finding_page(data,page)
        assert part["page"]==page
        assert part["total"]==1000
        ids.extend(x["record_id"] for x in part["items"])
    assert ids==[x["record_id"] for x in data]


@pytest.mark.parametrize("page",[-1,-100])
def test_negative_page_rejected(page):
    with pytest.raises(ValueError):
        finding_page(synthetic(),page)


def test_last_page_clamped_and_zero_items():
    assert finding_page(synthetic(81),500)["page"]==2
    assert len(finding_page(synthetic(81),500)["items"])==1
    assert finding_page([])["pages"]==1
    assert finding_page([])["items"]==[]


def test_search_status_casefold_source_only():
    records=synthetic(12)
    assert len(filter_findings(records,"OBS-0003"))==1
    assert len(filter_findings(records,"model-"))==12
    assert len(filter_findings(records,state="INDETERMINATE"))==6
    assert not filter_findings(records,"nonexisting")
    with pytest.raises(ValueError):
        filter_findings(records,state="AI_GENERATED")


def test_format_finding_preserves_raw_measurements_and_limits():
    record=synthetic(1)[0]
    out=format_finding(record,[{"image":"test.png","provenance":"user_asserted_not_verified"}])
    assert "Artık: 1.0 px" in out
    assert "INDETERMINATE" not in out or "NOT_TESTED" in out
    assert "user_asserted_not_verified" in out
    assert "NO_AI_ORIGIN_CONCLUSION" in out
    assert "AI tarafından üretildi" not in out
    record["explanation"]=["E"*200000]
    limited=format_finding(record)
    assert len(limited)<=MAX_PREVIEW_CHARS+150
    assert "Tam kayıt E03 JSON'unda" in limited


def test_json_is_never_parsed_as_probability():
    entry=synthetic(1)[0]
    assert "p-değeri: None" in format_finding(entry)
    assert "AI kökeni kararı: NO_AI_ORIGIN_CONCLUSION" in format_finding(entry)


def test_graph_transform_is_bounded_and_deterministic():
    assert graph_point(10,20,2,4,-3)==(24,37)
    assert clamp_zoom(0.01)==0.45
    assert clamp_zoom(99)==3.0
    assert clamp_zoom(1.0)==1.0
    with pytest.raises(ValueError):
        graph_point(0,0,float("nan"))
    with pytest.raises(ValueError):
        clamp_zoom(float("inf"))


def test_report_window_has_real_keyboard_and_graph_callbacks():
    source=inspect.getsource(ReviewWindow)
    assert "self.finding_query" in source
    assert "self.finding_filter" in source
    assert "self._change_page" in source
    assert "self._navigate_finding" in source
    assert "self._graph_pick" in source
    assert "self._zoom_graph" in source
    assert "self._pan_graph" in source
    assert "<Control-f>" in source
    assert "<F3>" in source
    assert "<Home>" in source


def test_measurement_plots_accept_start_window():
    assert "start=0" in inspect.signature(show_residuals).parameters["start"].__str__() or (
        inspect.signature(show_residuals).parameters["start"].default==0)
    assert inspect.signature(show_holdout).parameters["start"].default==0


def test_scientific_panels_page_without_recomputing_statistics():
    from aiforensics.science_panel_ui import navigable_chart
    source=inspect.getsource(navigable_chart)
    assert "current[0]" in source
    assert "show_holdout" in source
    assert "show_residuals" not in source or "renderer" in source
