"use client";

import { useState } from "react";

interface Comment {
  id: string;
  author: string;
  content: string;
  created_at: string;
}

export function useComments(_investigationId: string) {
  const [comments, setComments] = useState<Comment[]>([
    { id: "c-1", author: "Avery Park", content: "Checking upstream feeds.", created_at: new Date().toISOString() },
  ]);

  const addComment = (content: string) => {
    setComments((prev) => [
      { id: `c-${prev.length + 2}`, author: "You", content, created_at: new Date().toISOString() },
      ...prev,
    ]);
  };

  return { comments, addComment };
}
