"""In-memory stand-in for the Resolve scripting API (test use only)."""


class FakeTimeline:
    def __init__(self, name="Main", uid="tl-1", start=0, end=240, items=None):
        self.name, self.uid, self.start, self.end = name, uid, start, end
        self.markers = {}
        self.items = items or {"video": [[]], "audio": [[]], "subtitle": []}
        self.add_calls = []
        self.fail_add = False          # AddMarker returns False, no change
        self.silent_corrupt = False    # AddMarker "succeeds" but stores wrong name
        self.fail_delete = False
        self.break_readback_after_add = False
        self._add_count = 0

    def GetName(self): return self.name
    def GetUniqueId(self): return self.uid
    def GetStartFrame(self): return self.start
    def GetEndFrame(self): return self.end
    def GetSettings(self): return {"timelineFrameRate": "24"}
    def GetTrackCount(self, kind): return len(self.items.get(kind, []))
    def GetItemListInTrack(self, kind, index): return self.items[kind][index - 1]

    def GetMarkers(self):
        if self.break_readback_after_add and self._add_count:
            return None
        return {k: dict(v) for k, v in self.markers.items()}

    def AddMarker(self, frame, color, name, note, duration, custom):
        self.add_calls.append((frame, color, name, note, duration, custom))
        if self.fail_add or frame in self.markers:
            return False
        stored = "WRONG" if self.silent_corrupt else name
        self.markers[frame] = {"color": color, "name": stored, "note": note,
                               "duration": duration, "customData": custom}
        self._add_count += 1
        return True

    def DeleteMarkerAtFrame(self, frame):
        if self.fail_delete or frame not in self.markers:
            return False
        del self.markers[frame]
        return True


class FakeItem:
    def __init__(self, uid, name, start, end):
        self.uid, self.name, self.start, self.end = uid, name, start, end
    def GetUniqueId(self): return self.uid
    def GetName(self): return self.name
    def GetStart(self): return self.start
    def GetEnd(self): return self.end
    def GetDuration(self): return self.end - self.start
    def GetProperty(self): return {"Pan": 0.0, "Zoom": 1.0}


class FakeProject:
    def __init__(self, timeline, name="Proj", uid="pr-1"):
        self.timeline, self.name, self.uid = timeline, name, uid
        self.rendering = False
    def GetName(self): return self.name
    def GetUniqueId(self): return self.uid
    def GetCurrentTimeline(self): return self.timeline
    def IsRenderingInProgress(self): return self.rendering


class FakeManager:
    def __init__(self, project): self.project = project
    def GetCurrentProject(self): return self.project


class FakeResolve:
    def __init__(self, timeline=None, product="DaVinci Resolve Studio", version="20.0.0.1"):
        self.timeline = timeline or FakeTimeline()
        self.project = FakeProject(self.timeline)
        self.manager = FakeManager(self.project)
        self.product, self.version = product, version
    def GetProjectManager(self): return self.manager
    def GetVersionString(self): return self.version
    def GetProductName(self): return self.product
    def Fusion(self): return None
