class LlamaAgentic < Formula
  include Language::Python::Virtualenv

  desc "Local agentic AI CLI powered by llama.cpp"
  homepage "https://github.com/muhaimin/llama-agentic"
  url "https://files.pythonhosted.org/packages/source/l/llama-agentic/llama-agentic-0.1.0.tar.gz"
  sha256 "REPLACE_WITH_ACTUAL_SHA256_AFTER_PYPI_PUBLISH"
  license "MIT"

  depends_on "python@3.12"
  depends_on "llama.cpp"   # provides llama-server

  resource "openai" do
    url "https://files.pythonhosted.org/packages/source/o/openai/openai-1.0.0.tar.gz"
    sha256 "REPLACE"
  end

  resource "rich" do
    url "https://files.pythonhosted.org/packages/source/r/rich/rich-13.0.0.tar.gz"
    sha256 "REPLACE"
  end

  resource "click" do
    url "https://files.pythonhosted.org/packages/source/c/click/click-8.0.0.tar.gz"
    sha256 "REPLACE"
  end

  def install
    virtualenv_install_with_resources
  end

  test do
    assert_match "llama-agentic", shell_output("#{bin}/llama-agent --help")
  end
end
